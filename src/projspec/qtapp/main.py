import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
    QHBoxLayout,
    QDialog,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QUuid, QUrl
from PyQt5.QtGui import QIcon


class FileBrowserWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
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

                if item.is_dir():
                    child_item.setText(1, "Folder")
                    child_item.setText(2, "")
                    # Add dummy child to make it expandable
                    dummy = QTreeWidgetItem(child_item)
                    dummy.setText(0, "Loading...")
                else:
                    child_item.setText(1, "File")
                    try:
                        size = item.stat().st_size
                        child_item.setText(2, self.format_size(size))
                    except:
                        child_item.setText(2, "")

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

    def on_item_changed(self, item):
        import projspec

        if item.text(1) == "Folder":
            proj = projspec.Project(item.data(0, Qt.ItemDataRole.UserRole), walk=False)
            if proj.specs:
                print(proj.text_summary())
                html = f"<!DOCTYPE html><html><body>{proj._repr_html_()}</body></html>"
                self.detail.setHtml(html)
            else:
                self.detail.setHtml("<!DOCTYPE html><html><body></body></html>")

    def format_size(self, size):
        """Format file size in human-readable format"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"


def main():
    app = QApplication(sys.argv)
    window = FileBrowserWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
