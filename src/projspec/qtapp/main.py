"""Qt-based desktop UI for projspec - functional equivalent of the VSCode extension.

This app is a Python port of the `vsextension/` WebView UI.  A single
QMainWindow hosts a QWebEngineView rendering the same HTML/CSS/JS two-pane
layout (Library + Details) described in `vsextension/ACTIONS.md`, while the
Python side plays the role of the "extension host": it calls projspec APIs
directly (no subprocess), scans/creates/removes projects, and invokes
artifacts' ``make`` methods.

The look-and-feel is intentionally identical to the VSCode extension so the
two UIs diverge as little as possible.
"""

from __future__ import annotations

import json
import os
import os.path
from pathlib import Path
import subprocess
import sys
import warnings
import webbrowser

import projspec
from projspec.library import ProjectLibrary
from projspec.utils import class_infos

try:
    from PyQt5.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWebChannel import QWebChannel
    from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
    from PyQt5.QtWidgets import (
        QApplication,
        QFileDialog,
        QMainWindow,
        QMessageBox,
        QVBoxLayout,
        QWidget,
    )

    qt = True
except ImportError:
    # fallbacks to make this module importable and give a decent message
    QObject = object
    QMainWindow = object
    pyqtSignal = lambda *_: None
    pyqtSlot = lambda *_: lambda *_: None
    warnings.warn("PyQt5 not installed", ImportWarning)
    qt = False

from projspec.qtapp.views import get_panel_html


library = ProjectLibrary()


DEFAULT_CONFIG = {
    "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
    "scan_max_files": 100,
    "scan_max_size": 5000,
    "remote_artifact_status": False,
    "capture_artifact_output": True,
    "preferred_install_methods": ["conda", "pip"],
}


class JsBridge(QObject):
    """Exposed to the webview under the global name ``bridge``.

    Every JavaScript → Python call goes through :meth:`handleMessage`, which
    decodes a JSON string and hands the dict off to a single Python handler.
    Python → JavaScript calls emit :attr:`from_python` whose connected JS-side
    slot dispatches on ``type``.
    """

    from_python = pyqtSignal(str)  # JSON-encoded outbound message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handler = None

    def set_handler(self, handler) -> None:
        self._handler = handler

    @pyqtSlot(str)
    def handleMessage(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if self._handler:
            self._handler(data)

    def send(self, msg: dict) -> None:
        """Serialise ``msg`` and hand it to the connected JS listener."""
        self.from_python.emit(json.dumps(msg))


class ProjspecWindow(QMainWindow):
    """Single-window Qt app that mirrors the VSCode Project Library panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Projspec Browser")
        self.resize(1400, 820)

        self._info_data: dict = {}
        self._enum_members: dict = {}

        # Bridge + webview
        self._bridge = JsBridge(self)
        self._bridge.set_handler(self._on_message)
        self._view = QWebEngineView(self)
        channel = QWebChannel(self._view.page())
        channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(channel)

        # Qt WebEngine's default settings block a ``file://`` page from
        # loading webfonts referenced by ``data:`` URIs in its CSS.
        # Flipping these three switches tells Chromium to treat the page
        # the same way it would an HTTP page so ``@font-face`` resolves.
        settings = self._view.settings()
        for attr in (
            "LocalContentCanAccessRemoteUrls",
            "LocalContentCanAccessFileUrls",
            "ErrorPageEnabled",
        ):
            constant = getattr(
                QWebEngineSettings.WebAttribute
                if hasattr(QWebEngineSettings, "WebAttribute")
                else QWebEngineSettings,
                attr,
                None,
            )
            if constant is not None:
                settings.setAttribute(constant, True)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self.setCentralWidget(central)

        # Load the shared HTML UI.  We write to a temp file and ``setUrl``
        # it rather than calling ``setHtml``: the latter gives the page an
        # opaque origin that Chromium treats like a cross-origin document,
        # breaking anything that touches the page origin (external links,
        # relative anchors, future ``fetch`` calls).  Loading from a real
        # ``file://`` URL sidesteps all of that.
        import tempfile

        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".html", delete=False, encoding="utf-8"
        )
        tmp.write(get_panel_html())
        tmp.close()
        self._html_tempfile = tmp.name  # keep alive for Qt's loader
        self._view.setUrl(QUrl.fromLocalFile(tmp.name))

        # Kick off the initial load after the page has finished rendering.
        self._view.loadFinished.connect(self._on_load_finished)

        self._busy = 0

    def closeEvent(self, event) -> None:  # - Qt naming
        """Remove the temp HTML file on window close."""
        try:
            os.unlink(self._html_tempfile)
        except (OSError, AttributeError):
            pass
        super().closeEvent(event)

    # ── Busy indicator ──────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        """Tell the webview whether any in-flight operation is running.

        Uses a reference count so composed actions (scan + reload) keep the
        spinner up rather than flashing off between steps.
        """
        if busy:
            self._busy += 1
            if self._busy == 1:
                self._bridge.send({"type": "loading", "loading": True})
        else:
            self._busy = max(0, self._busy - 1)
            if self._busy == 0:
                self._bridge.send({"type": "loading", "loading": False})

    # ── Initial load ────────────────────────────────────────────────────────

    def _on_load_finished(self, ok: bool) -> None:  # - signal arg
        self._reload(initial=True)

    def _reload(self, initial: bool = False) -> None:
        self._set_busy(True)
        try:
            if initial or not self._info_data:
                self._info_data = class_infos()
                self._enum_members = _collect_enum_members()
            library.load()  # re-read the on-disk library file
            lib_dict = {
                url: proj.to_dict(compact=False)
                for url, proj in library.entries.items()
            }
            self._bridge.send(
                {
                    "type": "data",
                    "info": self._info_data,
                    "enums": self._enum_members,
                    "library": lib_dict,
                }
            )
        except Exception as e:
            QMessageBox.warning(self, "projspec", f"Reload failed: {e}")
        finally:
            self._set_busy(False)

    # ── Inbound message dispatcher ──────────────────────────────────────────

    def _on_message(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        try:
            if cmd == "ready":
                # Webview is up and re-asking for data.
                self._reload(initial=True)
            elif cmd == "reload":
                self._reload()
            elif cmd == "add":
                self._action_add()
            elif cmd == "configure":
                self._action_configure()
            elif cmd == "openWith":
                self._action_open_with(msg.get("tool", ""), msg.get("url", ""))
            elif cmd == "rescan":
                self._action_rescan(msg.get("url", ""))
            elif cmd == "createSpec":
                self._action_create_spec(msg.get("url", ""))
            elif cmd == "createSpecConfirmed":
                self._action_create_spec_confirmed(
                    msg.get("url", ""), msg.get("spec", "")
                )
            elif cmd == "removeFromLibrary":
                self._action_remove(msg.get("url", ""))
            elif cmd == "make":
                self._action_make(
                    msg.get("url", ""),
                    msg.get("spec"),
                    msg.get("artifactType", ""),
                    msg.get("name"),
                )
            elif cmd == "copyToLocal":
                QMessageBox.information(
                    self, "projspec", "Copy to local: not implemented"
                )
            elif cmd == "revealFile":
                self._action_reveal_file(msg.get("fn", ""))
        except Exception as e:
            QMessageBox.warning(self, "projspec", f"{cmd}: {e}")

    # ── Actions ─────────────────────────────────────────────────────────────

    def _action_add(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Add directory to library", str(Path.home())
        )
        if not path:
            return
        self._scan_and_reload(path, walk=True)

    def _action_configure(self) -> None:
        conf_dir = Path(
            os.environ.get("PROJSPEC_CONFIG_DIR")
            or (Path.home() / ".config" / "projspec")
        )
        conf_file = conf_dir / "projspec.json"
        if not conf_file.exists():
            conf_dir.mkdir(parents=True, exist_ok=True)
            conf_file.write_text(json.dumps(DEFAULT_CONFIG, indent=4))
        # Open in the OS default editor - there's no in-app editor here.
        _open_with_default(str(conf_file))
        # Show docs link so users are not left with a bare JSON file.
        webbrowser.open("https://projspec.readthedocs.io/en/latest/config.html")

    def _action_open_with(self, tool: str, url: str) -> None:
        local = _url_to_local(url)
        if tool == "vscode":
            _spawn_detached(["code", local])
        elif tool == "filebrowser":
            _open_with_default(local)
        elif tool == "pycharm":
            _spawn_detached(["pycharm", local, "nosplash", "dontReopenProjects"])
        elif tool == "jupyter":
            _spawn_detached(["jupyter", "lab", local])

    def _action_rescan(self, url: str) -> None:
        self._scan_and_reload(url, walk=False)

    def _action_create_spec(self, url: str) -> None:
        proj = library.entries.get(url)
        existing = set((proj.specs if proj is not None else {}) or {})
        creatable = sorted(
            name
            for name, entry in (self._info_data.get("specs") or {}).items()
            if entry.get("create") and name not in existing
        )
        creatable = sorted(
            name
            for name, entry in (self._info_data.get("specs") or {}).items()
            if entry.get("create") and name not in existing
        )
        if not creatable:
            QMessageBox.information(
                self, "Create spec", "No spec types available to create."
            )
            return
        self._bridge.send(
            {"type": "openCreateSpecModal", "url": url, "specs": creatable}
        )

    def _action_create_spec_confirmed(self, url: str, spec: str) -> None:
        if not spec:
            return
        self._set_busy(True)
        try:
            path = _url_to_local(url)
            proj = projspec.Project(path, walk=False)
            proj.create(spec)
            # Rescan and refresh.
            fresh = projspec.Project(path, walk=False)
            library.add_entry(path, fresh)
            self._reload()
        except Exception as e:
            QMessageBox.warning(self, "Create spec", f"Failed to create '{spec}': {e}")
        finally:
            self._set_busy(False)

    def _action_remove(self, url: str) -> None:
        if url in library.entries:
            del library.entries[url]
            library.save()
        self._reload()

    def _action_make(
        self,
        url: str,
        spec: str | None,
        artifact_type: str,
        name: str | None,
    ) -> None:
        qname = ".".join(p for p in (spec, artifact_type, name) if p)
        proj = library.entries.get(url)
        if proj is None:
            QMessageBox.warning(self, "Make", f"Project not found: {url}")
            return
        self._set_busy(True)
        try:
            art = proj.make(qname)
            QMessageBox.information(self, "Make", f"Done: {art}")
        except Exception as e:
            QMessageBox.warning(self, "Make", f"Make '{qname}' failed: {e}")
        finally:
            self._set_busy(False)

    def _action_reveal_file(self, fn: str) -> None:
        """Best-effort equivalent of the vscode ``revealInExplorer`` command."""
        if not fn:
            return
        local = fn[len("file://") :] if fn.startswith("file://") else fn
        # Remote artifacts can't be revealed.
        if "://" in local and not local.startswith("/"):
            QMessageBox.information(self, "Reveal", f"Remote file: {fn}")
            return
        matches = _expand_glob(local)
        if not matches:
            QMessageBox.information(self, "Reveal", f"No files match: {fn}")
            return
        target = matches[0]
        if len(matches) > 1:
            from PyQt5.QtWidgets import QInputDialog

            pick, ok = QInputDialog.getItem(
                self,
                "Reveal",
                f"{len(matches)} matches - pick one:",
                matches,
                0,
                False,
            )
            if not ok or not pick:
                return
            target = pick
        _open_with_default(os.path.dirname(target) or target)

    # ── Scan helper ─────────────────────────────────────────────────────────

    def _scan_and_reload(self, url: str, walk: bool) -> None:
        self._set_busy(True)
        try:
            path = _url_to_local(url) if url.startswith("file://") else url
            proj = projspec.Project(path, walk=walk)
            if walk:
                for child_url, child in (proj.children or {}).items():
                    if child.specs:
                        library.add_entry(child_url, child)
            if proj.specs:
                library.add_entry(path, proj)
            self._reload()
        except Exception as e:
            QMessageBox.warning(self, "Scan", f"Scan failed: {e}")
        finally:
            self._set_busy(False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url_to_local(url: str) -> str:
    """Strip ``file://`` prefix so the result is a plain path."""
    if url.startswith("file://"):
        return url[len("file://") :]
    return url


def _spawn_detached(cmd: list[str]) -> None:
    """Launch an external tool without blocking the Qt event loop."""
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        QMessageBox.warning(None, "projspec", f"Command not found: {cmd[0]}")
    except Exception as e:
        QMessageBox.warning(None, "projspec", f"Failed to run {cmd[0]}: {e}")


def _open_with_default(path: str) -> None:
    """Open ``path`` with the OS default handler."""
    try:
        if sys.platform == "darwin":
            subprocess.call(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.call(["xdg-open", path])
    except Exception:
        webbrowser.open(path)


def _expand_glob(pattern: str) -> list[str]:
    """Expand a glob pattern into an alphabetical list of concrete paths.

    Uses plain :mod:`glob` on the local filesystem.  For non-glob paths the
    list is ``[pattern]`` if the file exists, ``[]`` otherwise.
    """
    import glob

    if not any(c in pattern for c in "*?["):
        return [pattern] if os.path.exists(pattern) else []
    return sorted(glob.glob(pattern))


def _collect_enum_members() -> dict:
    """Mirror :code:`getEnumMembers` from the VSCode extension - maps
    snake-case enum class name to ``{MEMBER: value}``.  Used by the webview
    to display enum labels instead of raw integer values.
    """
    import importlib
    import pkgutil

    import projspec.artifact
    import projspec.content
    import projspec.utils as pu

    # Ensure every content / artifact module is imported so
    # ``Enum.__subclasses__()`` is complete.
    for pkg in (projspec.content, projspec.artifact):
        for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            try:
                importlib.import_module(m.name)
            except Exception:
                # A module that fails to import shouldn't stop enum collection.
                pass

    from projspec.utils import camel_to_snake

    out: dict[str, dict[str, int | str]] = {}
    seen: set[type] = set()

    def walk(cls: type) -> None:
        for sub in cls.__subclasses__():  # type: ignore[misc]
            if sub in seen:
                continue
            seen.add(sub)
            walk(sub)
            # ``sub`` inherits from ``projspec.utils.Enum`` (a subclass of
            # ``enum.Enum``) and so is iterable over its members.  Static type
            # checkers don't know this because we accept any ``type``.
            members = {m.name: m.value for m in sub}  # type: ignore[attr-defined]
            out[camel_to_snake(sub.__name__)] = members

    walk(pu.Enum)
    return out


def main() -> None:
    if not qt:
        print("No Qt bindings found - cannot continue")
        return
    app = QApplication(sys.argv)
    app.setApplicationName("projspec")
    icon_path = os.path.join(os.path.dirname(__file__), "../../../..", "logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = ProjspecWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
