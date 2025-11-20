import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QStyle,
    QHBoxLayout,
    QDockWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, pyqtSignal  # just Signal in PySide

from projspec.library import library


class FileBrowserWindow(QMainWindow):
    """A mini filesystem browser with project information

    The right-hand pane will populate with an HTML view of the selected item,
    if that item is a directory and can be interpreted as any project type.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library = Library()
        self.addDockWidget(Qt.BottomDockWidgetArea, self.library)

        self.setWindowTitle("Projspec Browser")
        self.setGeometry(100, 100, 950, 600)

        # Create tree widget
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Name", "Type", "Size"])
        self.tree.setColumnWidth(0, 400)
        self.tree.setColumnWidth(1, 50)

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
        layout.addWidget(self.tree)
        layout.addWidget(self.detail)
        central_widget.setLayout(layout)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Populate with home directory
        self.populate_tree()

    def populate_tree(self):
        """Populate the tree with the user's home directory"""
        home_path = Path.home()
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, home_path.name or str(home_path))
        root_item.setText(1, "Folder")
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(home_path))

        # Add a dummy child to make it expandable
        self.add_children(root_item, home_path)

        # Expand the root
        root_item.setExpanded(True)

    def add_children(self, parent_item, path):
        """Add child items for a directory"""
        try:
            path_obj = Path(path)

            # Get all items in directory
            items = sorted(
                path_obj.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
            )

            for item in items:
                # Skip hidden files (optional)
                if item.name.startswith("."):
                    continue

                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, item.name)
                child_item.setData(0, Qt.ItemDataRole.UserRole, str(item))

                style = app.style()
                if item.is_dir():
                    # TODO: change icon if it is in the library
                    child_item.setText(1, "Folder")
                    child_item.setText(2, "")
                    # Add dummy child to make it expandable
                    dummy = QTreeWidgetItem(child_item)
                    dummy.setText(0, "Loading...")
                    if str(item) in library.entries:
                        child_item.setIcon(
                            0, style.standardIcon(QStyle.SP_FileDialogInfoView)
                        )
                    else:
                        child_item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                else:
                    child_item.setText(1, "File")
                    try:
                        size = item.stat().st_size
                        child_item.setText(2, format_size(size))
                    except:
                        child_item.setText(2, "")
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

            # Get path from item data
            path = item.data(0, Qt.ItemDataRole.UserRole)

            # Add real children
            if path:
                self.add_children(item, path)
                self.statusBar().showMessage(f"Loaded: {path}")

    def on_item_changed(self, item: QTreeWidgetItem):
        import projspec

        if item.text(1) == "Folder":
            path = item.data(0, Qt.ItemDataRole.UserRole)
            proj = projspec.Project(path, walk=False)
            if proj.specs:
                style = app.style()
                item.setIcon(0, style.standardIcon(QStyle.SP_FileDialogInfoView))
                body = f"<!DOCTYPE html><html><body>{proj._repr_html_()}</body></html>"
                library.add_entry(path, proj)
            else:
                body = ""
            self.library.refresh()  # only on new item?
            self.detail.setHtml(f"<!DOCTYPE html><html><body>{body}</body></html>")


def format_size(self, size):
    """Format file size in human-readable format"""
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

        self.list = QTreeWidget(self)
        self.list.setHeaderLabels(["Path", "Types"])
        self.list.itemClicked.connect(self.on_selection_changed)
        self.list.setColumnWidth(0, 300)
        self.setWidget(self.list)

        self.refresh()

    def on_selection_changed(self, item: QTreeWidgetItem):
        path = item.text(0)
        proj = library.entries[path]
        body = f"<!DOCTYPE html><html><body>{proj._repr_html_()}</body></html>"
        self.project_selected.emit(body)

    def refresh(self):
        # any refresh reopens the pane if it was closed
        self.list.clear()
        for path in sorted(library.entries):
            data = library.entries[path]
            self.list.addTopLevelItem(QTreeWidgetItem([path, " ".join(data.specs)]))
        self.show()


def main():
    global app
    app = QApplication(sys.argv)
    window = FileBrowserWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
