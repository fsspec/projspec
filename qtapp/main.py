import json
import os.path
import posixpath
import sys
import webbrowser

import fsspec
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QPushButton,
    QComboBox,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QStyle,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QMessageBox,
    QSplitter,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import Qt, pyqtSignal, QObject, pyqtSlot, QUrl
from PyQt5.QtGui import QIcon

from projspec.library import ProjectLibrary
from projspec.utils import class_infos
import projspec

from views import get_library_html, get_details_html

library = ProjectLibrary()


# ---------------------------------------------------------------------------
# WebChannel bridge — receives messages from JS and dispatches to a handler
# ---------------------------------------------------------------------------


class JsBridge(QObject):
    """Exposed to JavaScript as ``bridge`` on the WebChannel.

    All JavaScript → Python calls go through ``handleMessage``.
    The handler callback is set by the owner widget.
    """

    message_received = pyqtSignal(str)  # emits raw JSON string

    def __init__(self, parent=None):
        super().__init__(parent)
        self._handler = None  # callable(dict)

    def set_handler(self, handler):
        self._handler = handler

    @pyqtSlot(str)
    def handleMessage(self, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if self._handler:
            self._handler(data)


def _make_web_view_with_channel(
    bridge: JsBridge,
) -> tuple[QWebEngineView, QWebChannel]:
    """Create a QWebEngineView with a QWebChannel pre-configured."""
    view = QWebEngineView()
    channel = QWebChannel(view.page())
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)
    return view, channel


# ---------------------------------------------------------------------------
# FileBrowserWindow
# ---------------------------------------------------------------------------


class FileBrowserWindow(QMainWindow):
    """A mini filesystem browser with project information.

    Left pane: filesystem tree.
    Right pane: project details as the VS Code-style HTML panel.
    Bottom dock: Library panel with the same HTML view as the VS Code extension.
    """

    def __init__(self, path=None, parent=None):
        super().__init__(parent)

        if path is None:
            path = os.path.expanduser("~")
        self.fs: fsspec.AbstractFileSystem
        self.path: str
        self.fs, self.path = fsspec.url_to_fs(path)

        self.setWindowTitle("Projspec Browser")
        self.setGeometry(100, 100, 1400, 700)

        # Left pane — file browser
        left = QVBoxLayout()

        nav_bar = QHBoxLayout()
        home_btn = QPushButton("⌂")
        home_btn.setToolTip("Home")
        home_btn.setFixedWidth(32)
        home_btn.clicked.connect(self.go_home)
        up_btn = QPushButton("↑")
        up_btn.setToolTip("Up")
        up_btn.setFixedWidth(32)
        up_btn.clicked.connect(self.go_up)
        self.path_text = QLineEdit(path)
        self.path_text.returnPressed.connect(self.path_set)
        nav_bar.addWidget(home_btn)
        nav_bar.addWidget(up_btn)
        nav_bar.addWidget(self.path_text)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.setColumnWidth(0, 250)
        self.tree.setColumnWidth(1, 50)
        left.addLayout(nav_bar)
        left.addWidget(self.tree)

        self.tree.itemExpanded.connect(self.on_item_expanded)
        self.tree.currentItemChanged.connect(self.on_item_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        left_widget = QWidget(self)
        left_widget.setLayout(left)

        # Middle pane — library
        self.library_widget = LibraryWidget(self)

        # Right pane — details
        self._detail_bridge = JsBridge(self)
        self._detail_bridge.set_handler(self._on_detail_message)
        self.detail, _ = _make_web_view_with_channel(self._detail_bridge)
        self.detail.setHtml(_empty_detail_html())

        self.library_widget.show_details.connect(self._show_project_details)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        splitter = QSplitter(Qt.Horizontal, central_widget)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.library_widget)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)

        outer = QHBoxLayout(central_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        central_widget.setLayout(outer)

        self.statusBar().showMessage("Ready")
        self.populate_tree()

    # ── Path / tree helpers ────────────────────────────────────────────────

    def path_set(self):
        try:
            self.fs, _ = fsspec.url_to_fs(self.path_text.text())
        except Exception:
            self.statusBar().showMessage("filesystem instantiation failed")
            return
        self.path = self.path_text.text()
        self.populate_tree()

    def go_home(self):
        self.path_text.setText(os.path.expanduser("~"))
        self.path_set()

    def go_up(self):
        # Strip protocol so dirname doesn't eat into "bucket" or the leading slash.
        stripped = str(self.fs._strip_protocol(self.path))
        parent_stripped = posixpath.dirname(stripped.rstrip("/"))
        # If stripping consumed everything (e.g. already at root), stay put.
        if not parent_stripped or parent_stripped == stripped:
            return
        self.path_text.setText(self.fs.unstrip_protocol(parent_stripped))
        self.path_set()

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        detail = item.data(0, Qt.ItemDataRole.UserRole)
        if detail and detail.get("type") == "directory":
            path = self.fs.unstrip_protocol(detail["name"])
            self.path_text.setText(path)
            self.path_set()

    def populate_tree(self):
        self.tree.clear()
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, self.path)
        self.add_children(root_item, self.path)
        root_item.setExpanded(True)

    def add_children(self, parent_item, path):
        try:
            details = self.fs.ls(path, detail=True)
            items = sorted(details, key=lambda x: (x["type"], x["name"].lower()))
            for item in items:
                name = item["name"].rsplit("/", 1)[-1]
                if name.startswith("."):
                    continue
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, name)
                child_item.setData(0, Qt.ItemDataRole.UserRole, item)
                style = app.style()
                if item["type"] == "directory":
                    dummy = QTreeWidgetItem(child_item)
                    dummy.setText(0, "Loading...")
                    if (
                        item["name"] in library.entries
                        or self.fs.unstrip_protocol(item["name"]) in library.entries
                    ):
                        child_item.setIcon(
                            0, style.standardIcon(QStyle.SP_FileDialogInfoView)
                        )
                    else:
                        child_item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                else:
                    child_item.setText(1, format_size(item["size"]))
                    child_item.setIcon(0, style.standardIcon(QStyle.SP_FileIcon))
        except PermissionError:
            error_item = QTreeWidgetItem(parent_item)
            error_item.setText(0, "Permission Denied")
            error_item.setForeground(0, Qt.GlobalColor.red)
        except Exception as e:
            error_item = QTreeWidgetItem(parent_item)
            error_item.setText(0, f"Error: {str(e)}")
            error_item.setForeground(0, Qt.GlobalColor.red)

    def on_item_expanded(self, item):
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.removeChild(item.child(0))
            path = item.data(0, Qt.ItemDataRole.UserRole)["name"]
            if path:
                self.add_children(item, path)
                self.statusBar().showMessage(f"Loaded: {path}")

    def on_item_changed(self, item: QTreeWidgetItem):
        if not item:
            return
        detail = item.data(0, Qt.ItemDataRole.UserRole)
        if detail is None:
            return
        if detail["type"] == "directory":
            path = self.fs.unstrip_protocol(detail["name"])
            proj = projspec.Project(path, walk=False, fs=self.fs)
            if proj.specs:
                style = app.style()
                item.setIcon(0, style.standardIcon(QStyle.SP_FileDialogInfoView))
                library.add_entry(path, proj)
                self.library_widget.refresh()
                self._show_project_details(path)
            else:
                self.detail.setHtml(_empty_detail_html())

    # ── Details panel ──────────────────────────────────────────────────────

    def _show_project_details(self, project_url: str, highlight_key: str = ""):
        proj = library.entries.get(project_url)
        if proj is None:
            return
        basename = project_url.split("/")[-1] or project_url
        html = get_details_html(basename, project_url, proj.to_dict(), highlight_key)
        self.detail.setHtml(html)

    def _on_detail_message(self, msg: dict):
        cmd = msg.get("command")
        if cmd == "openUrl":
            webbrowser.open(msg.get("url", ""))
        elif cmd == "makeArtifact":
            item = msg.get("item", {})
            qname = item.get("qname")
            project_url = item.get("projectUrl")
            if qname and project_url:
                self._make_artifact(project_url, qname)

    # ── Artifact make ──────────────────────────────────────────────────────

    def _make_artifact(self, project_url: str, qname: str):
        proj = library.entries.get(project_url)
        if proj is None:
            QMessageBox.warning(
                self, "Make Artifact", f"Project not found: {project_url}"
            )
            return
        try:
            self.statusBar().showMessage(f"Making {qname} in {project_url}…")
            art = proj.make(qname)
            self.statusBar().showMessage(f"Done: {art}")
        except Exception as e:
            self.statusBar().showMessage(f"Make failed: {e}")
            QMessageBox.warning(
                self, "Make Artifact", f"Failed to make '{qname}':\n{e}"
            )


# ---------------------------------------------------------------------------
# LibraryWidget  (replaces Library)
# ---------------------------------------------------------------------------


class LibraryWidget(QWidget):
    """Panel showing all scanned projects as an HTML view.

    Uses the same HTML view as the VS Code extension's Library panel.
    """

    show_details = pyqtSignal(str, str)  # emits (project_url, highlight_key)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._bridge = JsBridge(self)
        self._bridge.set_handler(self._on_message)
        self._view, _ = _make_web_view_with_channel(self._bridge)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self.setLayout(layout)

        self.refresh()

    def refresh(self, scroll_to: str | None = None):
        """Re-render the library HTML panel."""
        data = {url: proj.to_dict() for url, proj in library.entries.items()}
        info_data = class_infos()
        spec_names = list(info_data.get("specs", {}).keys())
        html = get_library_html(data, spec_names, scroll_to_project_url=scroll_to)
        self._view.setHtml(html)

    def _on_message(self, msg: dict):
        cmd = msg.get("command")

        if cmd == "openUrl":
            webbrowser.open(msg.get("url", ""))

        elif cmd == "scan":
            # Scan the current workspace (use the first top-level path in the tree)
            window = self.parent()
            if isinstance(window, FileBrowserWindow):
                path = window.path
                try:
                    proj = projspec.Project(path, walk=True, fs=window.fs)
                    for url, child in proj.children.items():
                        if child.specs:
                            library.add_entry(url, child)
                    if proj.specs:
                        library.add_entry(path, proj)
                    self.refresh(scroll_to=path)
                except Exception as e:
                    self.refresh()
                    QMessageBox.warning(self, "Scan", f"Scan failed:\n{e}")
            else:
                self.refresh()

        elif cmd == "removeProject":
            item = msg.get("item", {})
            project_url = item.get("infoData")
            if project_url and project_url in library.entries:
                del library.entries[project_url]
                library.save()
            self.refresh()

        elif cmd == "selectItem":
            item = msg.get("item", {})
            project_url = item.get("projectUrl")
            key = item.get("key", "")
            if project_url:
                self.show_details.emit(project_url, key)

        elif cmd == "makeArtifact":
            item = msg.get("item", {})
            qname = item.get("qname")
            project_url = item.get("projectUrl")
            if qname and project_url:
                window = self.parent()
                if isinstance(window, FileBrowserWindow):
                    window._make_artifact(project_url, qname)

        elif cmd == "createProject":
            project_type = msg.get("projectType", "")
            window = self.parent()
            if isinstance(window, FileBrowserWindow) and project_type:
                path = window.path
                try:
                    proj = projspec.Project(path, walk=False, fs=window.fs)
                    proj.create(project_type)
                    library.add_entry(path, proj)
                    self.refresh(scroll_to=path)
                except Exception as e:
                    self.refresh()
                    QMessageBox.warning(
                        self,
                        "Create Project",
                        f"Failed to create '{project_type}':\n{e}",
                    )

        elif cmd == "setBrowserPath":
            item = msg.get("item", {})
            project_url = item.get("infoData", "")
            this = self
            while this is not None:
                this = this.parent()
                if isinstance(this, FileBrowserWindow) and project_url:
                    this.path_text.setText(project_url)
                    this.path_set()
                    break
        elif cmd == "openInFileBrowser":
            item = msg.get("item", {})
            project_url = item.get("infoData", "")
            window = self.parent()
            if project_url:
                if project_url.startswith("file:///") or not "://" in project_url:
                    local_path = project_url.replace("file://", "")
                    open_path(local_path)
                else:
                    if isinstance(window, FileBrowserWindow):
                        window.statusBar().showMessage(
                            f"Cannot open in file browser: not a local path ({project_url})"
                        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_size(size: None | int) -> str:
    if size is None:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _empty_detail_html() -> str:
    return """<!DOCTYPE html><html><body style="background:#1e1e1e;color:#666;
font-family:-apple-system,sans-serif;padding:20px;">
<p>Select a project directory to see its details.</p></body></html>"""


def open_path(path: str):
    import subprocess

    if sys.platform == "darwin":
        subprocess.call(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.call(["xdg-open", path])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    global app
    app = QApplication(sys.argv)
    icon = QIcon(os.path.join(os.path.dirname(__file__), "..", "logo.png"))
    app.setWindowIcon(icon)
    window = FileBrowserWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
