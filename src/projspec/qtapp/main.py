import os.path
import sys
from pathlib import Path

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
    QDockWidget,
    QLineEdit,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, pyqtSignal  # just Signal in PySide

from projspec.library import library
import projspec


class FileBrowserWindow(QMainWindow):
    """A mini filesystem browser with project information

    The right-hand pane will populate with an HTML view of the selected item,
    if that item is a directory and can be interpreted as any project type.
    """

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.library = Library()
        if path is None:
            # implicitly local
            path = os.path.expanduser("~")
        self.fs, self.path = fsspec.url_to_fs(path)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.library)

        self.setWindowTitle("Projspec Browser")
        self.setGeometry(100, 100, 950, 600)

        left = QVBoxLayout()
        # Create tree widget
        self.path_text = QLineEdit(path)
        self.path_text.returnPressed.connect(self.path_set)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 50)
        left.addWidget(self.path_text)
        left.addWidget(self.tree)

        # Connect signals
        self.tree.itemExpanded.connect(self.on_item_expanded)
        self.tree.currentItemChanged.connect(self.on_item_changed)

        self.detail = QWebEngineView(self)
        # self.detail.load(QUrl("https://qt-project.org/"))
        self.detail.setFixedWidth(600)
        self.library.project_selected.connect(self.detail.setHtml)

        # Create central widget and layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.addLayout(left)
        layout.addWidget(self.detail)
        central_widget.setLayout(layout)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Populate with home directory
        self.populate_tree()

    def path_set(self):
        self.fs, _ = fsspec.url_to_fs(self.path_text.text())
        self.path = self.path_text.text()
        self.populate_tree()

    def populate_tree(self):
        """Populate the tree with the user's home directory"""
        self.tree.clear()
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, self.path)

        # Add a dummy child to make it expandable
        self.add_children(root_item, self.path)

        # Expand the root
        root_item.setExpanded(True)

    def add_children(self, parent_item, path):
        """Add child items for a directory"""
        try:
            # Get all items in directory
            details = self.fs.ls(path, detail=True)
            items = sorted(details, key=lambda x: (x["type"], x["name"].lower()))

            for item in items:
                # Skip hidden files (optional)
                name = item["name"].rsplit("/", 1)[-1]
                if name.startswith("."):
                    continue

                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, name)
                child_item.setData(0, Qt.ItemDataRole.UserRole, item)

                style = app.style()
                if item["type"] == "directory":
                    # TODO: change icon if it is in the library
                    # Add dummy child to make it expandable
                    dummy = QTreeWidgetItem(child_item)
                    dummy.setText(0, "Loading...")
                    if item["name"] in library.entries:
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
        """Handle item expansion - load children if not already loaded"""
        # Check if we need to load children (has dummy child)
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            # Remove dummy child
            item.removeChild(item.child(0))
            path = item.data(0, Qt.ItemDataRole.UserRole)["name"]
            if path:
                self.add_children(item, path)
                self.statusBar().showMessage(f"Loaded: {path}")

    def on_item_changed(self, item: QTreeWidgetItem):
        import projspec

        detail = item.data(0, Qt.ItemDataRole.UserRole)
        if detail["type"] == "directory":
            path = detail["name"]
            proj = projspec.Project(path, walk=False, fs=self.fs)
            if proj.specs:
                style = app.style()
                item.setIcon(0, style.standardIcon(QStyle.SP_FileDialogInfoView))
                body = f"<!DOCTYPE html><html><body>{proj._repr_html_()}</body></html>"
                library.add_entry(path, proj)
            else:
                body = ""
            self.library.refresh()  # only on new item?
            self.detail.setHtml(f"<!DOCTYPE html><html><body>{body}</body></html>")


def format_size(size: None | int) -> str:
    """Format file size in human-readable format"""
    if size is None:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class Library(QDockWidget):
    """Shows all scanned projects and allows filtering by various criteria"""

    project_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project Library")
        self.widget = QWidget(self)

        # search control
        swidget = QWidget(self.widget)
        upper_layout = QHBoxLayout()
        search = QPushButton("🔍")
        search.clicked.connect(self.on_search_clicked)
        clear = QPushButton("🧹")
        upper_layout.addWidget(search)
        upper_layout.addWidget(clear)
        upper_layout.addStretch()
        swidget.setLayout(upper_layout)

        # main list
        self.list = QTreeWidget(self.widget)
        self.list.setHeaderLabels(["Path", "Types"])
        self.list.itemClicked.connect(self.on_selection_changed)
        self.list.setColumnWidth(0, 300)

        # main layout
        layout = QVBoxLayout(self.widget)
        layout.addWidget(self.list)
        layout.addWidget(swidget)
        self.setWidget(self.widget)
        self.dia = SearchDialog(self)
        self.dia.accepted.connect(self.refresh)
        clear.clicked.connect(self.dia.clear)

        self.refresh()

    def on_search_clicked(self):
        self.dia.exec_()

    def on_selection_changed(self, item: QTreeWidgetItem):
        path = item.text(0)
        proj = library.entries[path]
        body = f"<!DOCTYPE html><html><body>{proj._repr_html_()}</body></html>"
        self.project_selected.emit(body)

    def refresh(self):
        # any refresh reopens the pane if it was closed
        self.list.clear()
        data = library.filter(self.dia.search_criteria)
        for path in sorted(data):
            self.list.addTopLevelItem(
                QTreeWidgetItem([path, " ".join(library.entries[path].specs)])
            )
        self.show()


class SearchItem(QWidget):
    """A single search criterion"""

    removed = pyqtSignal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        self.which = QComboBox(parent=self)
        self.which.addItems(["..", "spec", "artifact", "content"])
        self.which.currentTextChanged.connect(self.on_which_changed)
        layout.addWidget(self.which, 1)

        self.select = QComboBox(parent=self)
        self.select.addItem("..")
        layout.addWidget(self.select, 1)

        self.x = QPushButton("❌")
        self.x.clicked.connect(self.on_x_clicked)
        layout.addWidget(self.x)
        self.setLayout(layout)

    @property
    def criterion(self):
        sel = self.select.currentText()
        return (self.which.currentText(), sel) if sel != ".." else None

    def on_x_clicked(self, _):
        self.removed.emit(self)

    def on_which_changed(self, text):
        self.select.clear()
        self.select.addItem("..")
        if text == "spec":
            self.select.addItems([str(_) for _ in projspec.proj.base.registry])
        elif text == "artifact":
            self.select.addItems([str(_) for _ in projspec.artifact.base.registry])
        elif text == "content":
            self.select.addItems([str(_) for _ in projspec.content.base.registry])


class SearchDialog(QDialog):
    """Set search criteria"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.criteria = []

        right = QVBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        right.addWidget(ok)
        right.addWidget(cancel)
        right.addStretch(0)

        mini_layout = QHBoxLayout()
        add = QPushButton("+")
        add.clicked.connect(self.on_add)
        mini_layout.addWidget(add)
        mini_layout.addStretch(0)

        self.layout = QVBoxLayout()
        self.layout.addLayout(mini_layout)
        self.layout.addStretch(0)

        all_layout = QHBoxLayout(self)
        all_layout.addLayout(self.layout, 1)
        all_layout.addLayout(right)
        self.setLayout(all_layout)

    def on_add(self):
        search = SearchItem(self)
        search.removed.connect(self._on_search_removed)
        self.layout.insertWidget(0, search)
        self.criteria.append(search)

    @property
    def search_criteria(self):
        return [_.criterion for _ in self.criteria if _.criterion is not None]

    def clear(self):
        for item in self.criteria:
            self.layout.removeWidget(item)
        self.criteria = []
        self.accepted.emit()

    def _on_search_removed(self, search_widget):
        self.layout.removeWidget(search_widget)
        self.criteria.remove(search_widget)


def main():
    global app
    app = QApplication(sys.argv)
    window = FileBrowserWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
