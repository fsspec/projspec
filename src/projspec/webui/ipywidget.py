"""Jupyter / marimo widget representation of :class:`ProjectLibrary`.

This module owns the *host* side of the shared webui transport for the
Jupyter Notebook / JupyterLab / VSCode-notebook / Colab / marimo
environments.  It builds an :mod:`anywidget` ``AnyWidget`` that loads the
shared HTML, CSS and JS from :mod:`projspec.webui` and drives it from
Python with the same command vocabulary as the VSCode extension and the
Qt app.

Only :mod:`anywidget` is required — :mod:`ipywidgets` is **not** needed,
which means the widget runs under marimo as well as classic Jupyter.

Current limitations
-------------------

The shared JS uses ``document.getElementById`` with global IDs (``#app``,
``#projects``, etc.), which is fine for a single widget per notebook but
means two widgets on the same page would fight for those IDs.  This
matches the existing VSCode/Qt/PyCharm design; scoping is a follow-up.

The widget is interactive: the toolbar's *Add / Reload / Configure*
buttons, the kebab menu (Rescan / Create spec / Remove from library /
Open with …), and the per-artifact ``Make`` button all round-trip to the
Python kernel and modify the underlying :class:`ProjectLibrary`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from projspec.webui import chrome_icons, get_panel_css, get_panel_js

if TYPE_CHECKING:  # pragma: no cover - type-only import
    from projspec.library import ProjectLibrary


# ---------------------------------------------------------------------------
#  ESM module text (anywidget _esm)
# ---------------------------------------------------------------------------
#
# anywidget loads ``_esm`` as a JavaScript module whose default export is
# ``{render({model, el}) -> cleanup?}``.  We embed the shared panel HTML
# into ``el``, install a transport that proxies to the widget's
# ``model.send`` / ``model.on('msg:custom', ...)``, and then execute the
# shared panel script.
#
# Each render re-installs the transport on ``window.projspecTransport`` and
# re-runs the panel JS.  See module docstring for the single-instance
# caveat this carries.
#
# The panel HTML must be inserted inline (not via an iframe) so the host
# CSS variables propagate from the hosting notebook / JupyterLab theme.

# NOTE: kept as a triple-quoted Python string.  The JS template-string
# placeholders ${...} inside the code below are the *JavaScript* kind and
# must stay literal - we use a non-f-string so Python does not touch them.

_ESM_TEMPLATE = r"""
const PANEL_HTML_BODY = __PANEL_HTML_BODY__;
const PANEL_CSS = __PANEL_CSS__;
const PANEL_JS = __PANEL_JS__;
const CHROME_ICONS = __CHROME_ICONS__;

export function render({ model, el }) {
    // Per-widget root element.  We install it on ``window.projspecRoot``
    // before evaluating the shared panel script; ``panel.js`` scopes every
    // element lookup to that root so multiple widget instances (or stale
    // nodes from an earlier render) don't fight over the same global IDs.
    const root = document.createElement('div');
    root.className = 'projspec-root';
    root.style.width = '100%';
    root.innerHTML = PANEL_HTML_BODY;
    // Install the chrome-icons map and the scoped-root reference the panel
    // script reads at startup.
    window.__PROJSPEC_CHROME_ICONS__ = CHROME_ICONS;
    window.projspecRoot = root;

    // Transport: JS -> kernel via model.send; kernel -> JS via
    // msg:custom.  The panel script will call transport.onReady(dispatch)
    // exactly once; we stash the dispatcher so late-arriving messages
    // are delivered correctly.
    let dispatcher = null;
    const inbox = [];
    function onHostMessage(msg) {
        if (dispatcher) dispatcher(msg);
        else inbox.push(msg);
    }
    model.on('msg:custom', onHostMessage);

    window.projspecTransport = {
        send: (msg) => model.send(msg),
        onReady: (dispatch) => {
            dispatcher = dispatch;
            while (inbox.length) dispatcher(inbox.shift());
        },
    };

    // Scoped stylesheet (per-widget <style>) so repeated widget renders
    // don't pile up.  The CSS uses :root-ish global rules on body/#app,
    // but since those IDs are re-used per render and the widget is a
    // single-instance tool, this is tolerable.
    const styleEl = document.createElement('style');
    styleEl.textContent = PANEL_CSS;
    root.prepend(styleEl);
    el.appendChild(root);

    // Finally, evaluate the panel script in the window scope.  Using new
    // Function + .call(window) gives it ``this === window`` and access
    // to document.getElementById - same environment the VSCode/Qt hosts
    // provide.
    try {
        new Function(PANEL_JS).call(window);
    } catch (err) {
        console.error('projspec panel script failed:', err);
        const pre = document.createElement('pre');
        pre.style.color = '#c66';
        pre.textContent = String(err && err.stack || err);
        el.appendChild(pre);
    }

    return () => {
        model.off('msg:custom', onHostMessage);
        try { el.removeChild(root); } catch {}
    };
}
"""


def _build_esm() -> str:
    """Assemble the ESM module text, with the shared resources embedded.

    Each resource is JSON-encoded so the resulting module is a syntactically
    valid JS string literal, which sidesteps any quoting issues with the
    panel HTML / CSS / JS.
    """
    from projspec.webui import get_panel_html

    # We only want the <body> inner HTML, not the full <html>...<body>
    # envelope: the notebook already has one.  Ask the webui helper for a
    # rendered document (icons resolved, no bootstrap, no extra head) and
    # cut the body out.
    icons = chrome_icons()
    html = get_panel_html()
    # Leave the CSS/JS out of the body: we embed them separately into the
    # ESM so we control their execution order.  The rendered HTML has a
    # `<style>...</style>` block (full CSS) and a `<script>...</script>`
    # block (full JS) inside the body; strip both.
    body_start = html.find("<body>")
    body_end = html.rfind("</body>")
    if body_start < 0 or body_end < 0:
        raise RuntimeError("panel.html missing <body>..</body>")
    body_inner = html[body_start + len("<body>") : body_end]
    # get_panel_html emits <style>{css}</style> in <head>, but the body also
    # ends with <script>{js}</script> - strip that.  We find the *last*
    # <script>...</script> pair to avoid chewing on inline bootstrap JS
    # (there's none here).
    last_script = body_inner.rfind("<script>")
    if last_script >= 0:
        body_inner = (
            body_inner[:last_script]
            + body_inner[body_inner.find("</script>", last_script) + len("</script>") :]
        )

    return (
        _ESM_TEMPLATE.replace("__PANEL_HTML_BODY__", json.dumps(body_inner))
        .replace("__PANEL_CSS__", json.dumps(get_panel_css()))
        .replace("__PANEL_JS__", json.dumps(get_panel_js()))
        .replace("__CHROME_ICONS__", json.dumps(icons))
    )


# ---------------------------------------------------------------------------
#  Widget class
# ---------------------------------------------------------------------------


def _build_widget(library: "ProjectLibrary"):
    """Construct the anywidget-backed DOMWidget for ``library``.

    Import is deferred so :mod:`projspec.library` stays usable in
    environments where :mod:`anywidget` is not installed.
    """
    try:
        import anywidget
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError(
            "The ipywidget representation of ProjectLibrary requires the "
            "'anywidget' package.  Install it with "
            "``pip install projspec[ipywidget]`` or "
            "``pip install anywidget``."
        ) from exc

    class ProjectLibraryWidget(anywidget.AnyWidget):
        """Interactive ipywidget rendering of a :class:`ProjectLibrary`.

        Mirrors the vsextension / qtapp UI: Library list on the left,
        Details on the right.  Commands (add, reload, rescan, make, …)
        are round-tripped to the Python kernel and modify the underlying
        library in place.
        """

        _esm = _build_esm()
        # CSS is embedded in the ESM; anywidget ignores an empty _css.
        _css = ""

        # No traitlets state: the widget exchanges messages via
        # ``send`` / ``msg:custom`` instead of syncing a model attribute.

        def __init__(self, library_obj: "ProjectLibrary", **kwargs: Any):
            super().__init__(**kwargs)
            self._library = library_obj
            self._info_data: dict[str, Any] = {}
            self._enum_members: dict[str, Any] = {}
            self.on_msg(self._on_frontend_message)

        # --- Inbound frontend -> Python ---------------------------------
        def _on_frontend_message(
            self, _widget: Any, content: Any, _buffers: Any
        ) -> None:
            if not isinstance(content, dict):
                return
            cmd = content.get("cmd")
            try:
                if cmd == "ready":
                    self._send_initial_data()
                elif cmd == "reload":
                    self._reload()
                elif cmd == "add":
                    self._offer_add()
                elif cmd == "addConfirmed":
                    self._add_confirmed(
                        content.get("path", ""),
                        content.get("storageOptions", ""),
                    )
                elif cmd == "configure":
                    _open_config_file(self._toast)
                elif cmd == "rescan":
                    self._rescan(content.get("url", ""))
                elif cmd == "createSpec":
                    self._offer_create_spec(content.get("url", ""))
                elif cmd == "createSpecConfirmed":
                    self._create_spec_confirmed(
                        content.get("url", ""), content.get("spec", "")
                    )
                elif cmd == "removeFromLibrary":
                    url = content.get("url", "")
                    self._library.entries.pop(url, None)
                    if self._library.auto_save:
                        self._library.save()
                    self._send_initial_data()
                elif cmd == "make":
                    self._make(
                        content.get("url", ""),
                        content.get("spec"),
                        content.get("artifactType", ""),
                        content.get("name"),
                    )
                elif cmd == "openWith":
                    _open_with(
                        content.get("tool", ""),
                        content.get("url", ""),
                        self._toast,
                    )
                elif cmd == "revealFile":
                    _reveal_file(content.get("fn", ""), self._toast)
                elif cmd == "copyToLocal":
                    self._toast("Copy to local: not implemented")
            except Exception as exc:  # log but never raise into the kernel
                self._toast(f"{cmd}: {exc!r}")

        # --- Outbound Python -> frontend --------------------------------
        def _send_initial_data(self) -> None:
            from projspec.utils import class_infos

            if not self._info_data:
                self._info_data = class_infos()
                self._enum_members = _collect_enum_members()

            lib_dict = {
                url: proj.to_dict(compact=False)
                for url, proj in self._library.entries.items()
            }
            self.send(
                {
                    "type": "data",
                    "info": self._info_data,
                    "enums": self._enum_members,
                    "library": lib_dict,
                }
            )

        def _reload(self) -> None:
            """Re-read the on-disk library, but only when doing so won't
            destroy in-memory state.

            ``ProjectLibrary.load()`` resets ``self.entries = {}`` when the
            backing file is missing, which would wipe an in-memory-only
            library (the common case when the widget is driven from user
            code, e.g. ``library.add_entry(...)`` in a cell).  We only
            reload from disk when a backing file actually exists.
            """
            import os

            path = self._library.path
            if path and os.path.isfile(path):
                self._library.load()
            self._send_initial_data()

        def _set_busy(self, busy: bool) -> None:
            self.send({"type": "loading", "loading": bool(busy)})

        def _toast(self, message: str) -> None:
            """Surface a short status message to the user.

            In a notebook we just print so the message lands in the cell
            output; we deliberately do not raise.  The Qt app uses a modal
            dialog here; the widget has no equivalent without more JS.
            """
            print(f"[projspec] {message}")

        # --- Action helpers --------------------------------------------
        def _offer_add(self) -> None:
            """Ask the frontend to open the text-entry modal for a new
            project path."""
            self.send({"type": "openAddModal"})

        def _add_confirmed(self, path: str, storage_options: str = "") -> None:
            from projspec.utils import scan_glob

            path = (path or "").strip()
            if not path:
                return
            self._set_busy(True)
            try:
                found = False
                for proj in scan_glob(
                    path,
                    storage_options=storage_options,
                    walk=True,
                    add_to_library=False,
                ):
                    found = True
                    key = proj.fs.unstrip_protocol(proj.url)
                    self._library.add_entry(key, proj)
                    for child in (proj.children or {}).values():
                        if child.specs:
                            child_key = child.fs.unstrip_protocol(child.url)
                            self._library.add_entry(child_key, child)
                if not found:
                    self._toast(f"No directories found: {path}")
                    return
                self._send_initial_data()
            except Exception as exc:
                self._toast(f"Scan failed: {exc}")
            finally:
                self._set_busy(False)

        def _resolve_entry_path(self, url: str) -> str | None:
            """Return the path used to re-open the library entry *url*.

            The path must keep its protocol so remote projects (``memory://``,
            ``s3://``, …) re-open against the right filesystem.  We prefer the
            library key *url* when it already carries a protocol - it is the
            authoritative, protocol-qualified identifier the UI holds, and is
            reliable even when an older serialised library reconstructed the
            entry's filesystem as local.  Otherwise we use the stored project's
            protocol-qualified URL (``fs.unstrip_protocol(proj.url)``), since
            ``proj.path``/``proj.url`` have the protocol stripped by
            ``fsspec.url_to_fs`` (e.g. ``/proj`` for ``memory://proj``) and a
            bare path would resolve against the *local* filesystem.

            The library key is otherwise an opaque identity used by the UI;
            reusing it as a path breaks for entries keyed on a basename or
            relative sub-path (e.g. walked children added under the library
            root), so we only fall back to ``_url_to_local`` when there is no
            matching entry.
            """
            if url and "://" in url:
                return url
            proj = self._library.entries.get(url)
            if proj is not None and getattr(proj, "path", None):
                try:
                    return proj.fs.unstrip_protocol(proj.url)
                except Exception:
                    return proj.path
            # Fall back to the URL, minus any ``file://`` scheme prefix, so
            # the caller still gets *something* usable when there is no
            # matching entry (e.g., the UI is about to create one).
            return _url_to_local(url) if url else None

        def _entry_storage_options(self, url: str) -> dict:
            """Storage options stored on the library entry *url* (or ``{}``).

            Remote projects (s3://, gcs://, authenticated http, …) need their
            ``storage_options`` to be re-supplied when reconstructing the
            ``Project`` on rescan, otherwise the filesystem access fails.
            """
            proj = self._library.entries.get(url)
            return dict(getattr(proj, "storage_options", None) or {})

        def _rescan(self, url: str) -> None:
            """Re-run ``Project(...)`` for the entry *url* and replace it.

            The library key is preserved verbatim so the UI's identity for
            the entry does not drift (the JS selection state is keyed on
            that url).  Crucially, the *path* used for the new ``Project``
            is taken from the stored entry's ``proj.path`` - not from the
            library key - because library keys may be opaque identifiers
            (e.g. a walked child's basename) that would resolve against
            the kernel's cwd if passed to ``Project(...)``.
            """
            import projspec

            if not url:
                return
            path = self._resolve_entry_path(url)
            if not path:
                self._toast(f"Cannot resolve path for {url}")
                return
            self._set_busy(True)
            try:
                proj = projspec.Project(
                    path,
                    walk=False,
                    storage_options=self._entry_storage_options(url),
                )
                # Keep the *original* library key so we don't duplicate the
                # entry under a different protocol prefix.
                self._library.entries[url] = proj
                if self._library.auto_save:
                    self._library.save()
                self._send_initial_data()
            finally:
                self._set_busy(False)

        def _offer_create_spec(self, url: str) -> None:
            proj = self._library.entries.get(url)
            existing = set((proj.specs if proj is not None else {}) or {})
            creatable = sorted(
                name
                for name, entry in (self._info_data.get("specs") or {}).items()
                if entry.get("create") and name not in existing
            )
            if not creatable:
                self._toast("No spec types available to create.")
                return
            self.send({"type": "openCreateSpecModal", "url": url, "specs": creatable})

        def _create_spec_confirmed(self, url: str, spec: str) -> None:
            if not spec or not url:
                return
            import projspec

            path = self._resolve_entry_path(url)
            if not path:
                self._toast(f"Cannot resolve path for {url}")
                return
            self._set_busy(True)
            try:
                so = self._entry_storage_options(url)
                proj = projspec.Project(path, walk=False, storage_options=so)
                proj.create(spec)
                fresh = projspec.Project(path, walk=False, storage_options=so)
                # Same key-preservation rule as _rescan.
                self._library.entries[url] = fresh
                if self._library.auto_save:
                    self._library.save()
                self._send_initial_data()
            finally:
                self._set_busy(False)

        def _make(
            self,
            url: str,
            spec: str | None,
            artifact_type: str,
            name: str | None,
        ) -> None:
            qname = ".".join(p for p in (spec, artifact_type, name) if p)
            proj = self._library.entries.get(url)
            if proj is None:
                self._toast(f"Project not found: {url}")
                return
            # Guard against a Project whose stored ``path`` is not absolute
            # (possible for library entries that were keyed under a walked
            # child's basename pre-fix).  Artifacts launch subprocesses with
            # ``cwd=self.proj.path``; a relative cwd would resolve against
            # the kernel's working directory - i.e. the notebook's launch
            # directory - instead of the project's own location.  Absolutize
            # against the library key (which, for entries added via the
            # widget, is the project's ``unstrip_protocol(url)``).
            import os

            if proj.path and not os.path.isabs(proj.path):
                fallback = _url_to_local(url)
                if os.path.isabs(fallback):
                    proj.path = fallback
                else:
                    proj.path = os.path.abspath(proj.path)
                # Keep proj.url in sync so any fs.ls() calls still work.
                proj.url = proj.path
            self._set_busy(True)
            try:
                art = proj.make(qname)
                self._toast(f"make {qname}: {art}")
            finally:
                self._set_busy(False)

    return ProjectLibraryWidget(library)


# ---------------------------------------------------------------------------
#  Subprocess-backed helpers shared by the Python widget host.
# ---------------------------------------------------------------------------
#
# These mirror the equivalent code in ``qtapp/main.py``.  Every action that
# *has* a meaningful effect in a notebook kernel is implemented here; the
# few that cannot (picking a folder with a native dialog, opening a modal
# dialog, etc.) are handled via additional frontend messages above.


def _url_to_local(url: str) -> str:
    """Strip a leading ``file://`` from *url* so the result is a plain path."""
    if url.startswith("file://"):
        return url[len("file://") :]
    return url


def _spawn_detached(cmd: list[str], toast) -> None:
    """Launch an external tool without blocking the kernel.

    Errors are reported via the supplied *toast* callback - we don't want
    a failed spawn to propagate as an exception into the cell output.
    """
    import subprocess

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        toast(f"Command not found: {cmd[0]}")
    except Exception as exc:
        toast(f"Failed to run {cmd[0]}: {exc!r}")


def _open_with_default(path: str, toast) -> None:
    """Open *path* with the OS default handler (equivalent of double-click)."""
    import os
    import subprocess
    import sys

    try:
        if sys.platform == "darwin":
            subprocess.call(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.call(["xdg-open", path])
    except Exception as exc:
        toast(f"Could not open {path}: {exc!r}")


def _open_with(tool: str, url: str, toast) -> None:
    """Dispatch the *Open with …* kebab-menu choices.

    Supported tools match the other projspec UIs:

    ``vscode``
        ``code <path>``
    ``filebrowser``
        OS file manager (``xdg-open`` / ``open`` / Explorer)
    ``pycharm``
        ``pycharm <path> nosplash dontReopenProjects``
    ``jupyter``
        ``jupyter lab <path>``
    """
    local = _url_to_local(url)
    if tool == "vscode":
        _spawn_detached(["code", local], toast)
    elif tool == "filebrowser":
        _open_with_default(local, toast)
    elif tool == "pycharm":
        _spawn_detached(["pycharm", local, "nosplash", "dontReopenProjects"], toast)
    elif tool == "jupyter":
        _spawn_detached(["jupyter", "lab", local], toast)
    else:
        toast(f"Unknown openWith tool: {tool!r}")


def _reveal_file(fn: str, toast) -> None:
    """Reveal *fn* (a file path or glob) in the OS file manager.

    When *fn* contains a wildcard we open the first match; if nothing
    matches we report it to the user.  Remote URLs are ignored.
    """
    import glob
    import os

    if not fn:
        return
    local = fn[len("file://") :] if fn.startswith("file://") else fn
    if "://" in local and not local.startswith("/"):
        toast(f"Remote file cannot be revealed: {fn}")
        return
    if any(c in local for c in "*?["):
        matches = sorted(glob.glob(local))
    else:
        matches = [local] if os.path.exists(local) else []
    if not matches:
        toast(f"No files match: {fn}")
        return
    target = matches[0]
    _open_with_default(os.path.dirname(target) or target, toast)


def _open_config_file(toast) -> None:
    """Open the projspec JSON config in the OS default editor.

    Creates the directory and a minimal default config file if they do
    not exist yet, mirroring the ``qtapp`` and VSCode extension
    ``Configure`` actions.
    """
    import json
    import os
    from pathlib import Path

    conf_dir = Path(
        os.environ.get("PROJSPEC_CONFIG_DIR") or (Path.home() / ".config" / "projspec")
    )
    conf_file = conf_dir / "projspec.json"
    if not conf_file.exists():
        try:
            conf_dir.mkdir(parents=True, exist_ok=True)
            conf_file.write_text(
                json.dumps(
                    {
                        "scan_types": [
                            ".py",
                            ".yaml",
                            ".yml",
                            ".toml",
                            ".json",
                            ".md",
                        ],
                        "scan_max_files": 100,
                        "scan_max_size": 5000,
                        "remote_artifact_status": False,
                        "capture_artifact_output": True,
                        "preferred_install_methods": ["conda", "pip"],
                    },
                    indent=4,
                )
            )
        except OSError as exc:
            toast(f"Could not create {conf_file}: {exc!r}")
            return
    _open_with_default(str(conf_file), toast)
    toast(
        "ProjSpec configuration — see the docs for all available fields: "
        "https://projspec.readthedocs.io/en/latest/config.html"
    )


def _collect_enum_members() -> dict[str, dict[str, int | str]]:
    """Mirror ``qtapp.main._collect_enum_members``.

    Walks every :class:`projspec.utils.Enum` subclass and returns
    ``{snake_case_name: {MEMBER: value}}``.  Used by the shared panel JS
    to render enum-valued fields with their member labels instead of
    their raw integer values.
    """
    import importlib
    import pkgutil

    import projspec.artifact
    import projspec.content
    import projspec.utils as pu

    for pkg in (projspec.content, projspec.artifact):
        for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            try:
                importlib.import_module(m.name)
            except Exception:
                # Optional deps may keep some modules from loading; that's
                # fine - we just skip them for the enum map.
                pass

    from projspec.utils import camel_to_snake

    out: dict[str, dict[str, int | str]] = {}
    seen: set[type] = set()

    def walk(cls: type) -> None:
        for sub in cls.__subclasses__():
            if sub in seen:
                continue
            seen.add(sub)
            walk(sub)
            members = {m.name: m.value for m in sub}  # type: ignore[attr-defined]
            out[camel_to_snake(sub.__name__)] = members

    walk(pu.Enum)
    return out


def make_widget(library: "ProjectLibrary"):
    """Return an anywidget-backed DOMWidget for ``library``.

    Public entry point used by :meth:`ProjectLibrary.widget`.
    """
    return _build_widget(library)


__all__ = ["make_widget"]
