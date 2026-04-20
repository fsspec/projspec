"""Textual TUI for projspec — terminal equivalent of qtapp.

Three-pane layout:
  Left   — Filesystem tree (navigate directories, single-click parses & adds to library)
  Centre — Library panel  (all scanned projects with collapsible spec/content/artifact tree)
  Right  — Details panel  (full project detail tree for the selected project)

Key bindings
  h / Home     go to home directory
  u / Up       go up one directory level
  s            scan current directory (walk=True)
  c            create a project type in the current directory
  q / Ctrl+C   quit
"""

from __future__ import annotations

import os
import posixpath
import sys
from pathlib import Path

import fsspec

import projspec
from projspec.library import ProjectLibrary
from projspec.utils import class_infos

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Tree,
)
from textual.widgets.tree import TreeNode
from textual.css.query import NoMatches


# ---------------------------------------------------------------------------
# Shared global library (mirrors qtapp)
# ---------------------------------------------------------------------------

library = ProjectLibrary()

# ---------------------------------------------------------------------------
# Colours / role mapping (mirrors qtapp CSS colours)
# ---------------------------------------------------------------------------

ROLE_COLOUR = {
    "project": "bold #dcb67a",
    "spec": "#dcdcaa",
    "content": "#4ec9b0",
    "artifact": "#ce9178",
    "field": "#cccccc",
    "value": "italic #9cdcfe",
}


def _role_markup(text: str, role: str) -> str:
    colour = ROLE_COLOUR.get(role, "#cccccc")
    return f"[{colour}]{text}[/]"


# ---------------------------------------------------------------------------
# Helpers: build a node tree from a project dict (reuses qtapp logic)
# ---------------------------------------------------------------------------

_SKIP_KEYS = {"klass", "proc", "storage_options", "children", "url", "_html"}


def _scalar(v) -> str:
    if v is None:
        return "null"
    return str(v)


def _build_detail_nodes(obj, role: str, qname: str, project_url: str) -> list[dict]:
    """Recursively turn a project dict into a list of node dicts."""
    if obj is None:
        return []

    if isinstance(obj, list):
        result = []
        for i, item in enumerate(obj):
            if isinstance(item, dict):
                result.append(
                    {
                        "label": str(i),
                        "role": role,
                        "children": _build_detail_nodes(
                            item, role, f"{qname}.{i}", project_url
                        ),
                    }
                )
            else:
                result.append({"label": _scalar(item), "role": "field"})
        return result

    if not isinstance(obj, dict):
        return [{"label": _scalar(obj), "role": "field"}]

    nodes = []
    for key, value in obj.items():
        if key in _SKIP_KEYS:
            continue
        child_path = f"{qname}.{key}" if qname else key

        # Container keys — inline with corrected role
        if key in ("specs", "_contents", "contents", "_artifacts", "artifacts"):
            child_role = (
                "spec"
                if key == "specs"
                else "content"
                if key in ("_contents", "contents")
                else "artifact"
            )
            nodes.extend(_build_detail_nodes(value, child_role, qname, project_url))
            continue

        # Artifact special handling
        if role == "artifact":
            if isinstance(value, str) or value is None:
                nodes.append(
                    {
                        "label": key,
                        "role": "artifact",
                        "qname": child_path,
                        "project_url": project_url,
                        "can_make": True,
                    }
                )
            elif isinstance(value, dict):
                entries = list(value.items())
                all_strings = all(isinstance(v, (str, type(None))) for _, v in entries)
                if all_strings:
                    named_children = [
                        {
                            "label": name,
                            "role": "artifact",
                            "qname": f"{child_path}.{name}",
                            "project_url": project_url,
                            "can_make": True,
                        }
                        for name, _ in entries
                    ]
                    nodes.append(
                        {
                            "label": key,
                            "role": "artifact",
                            "children": named_children or None,
                        }
                    )
                else:
                    children = _build_detail_nodes(
                        value, "field", child_path, project_url
                    )
                    nodes.append(
                        {
                            "label": key,
                            "role": "artifact",
                            "qname": child_path,
                            "project_url": project_url,
                            "children": children or None,
                            "can_make": True,
                        }
                    )
            continue

        # Scalar leaf
        if value is None or not isinstance(value, (dict, list)):
            nodes.append(
                {
                    "label": key,
                    "value": _scalar(value),
                    "role": role if role in ("spec", "content") else "field",
                }
            )
            continue

        if isinstance(value, list):
            if all(not isinstance(v, dict) for v in value):
                array_children = [{"label": _scalar(v), "role": "field"} for v in value]
                nodes.append(
                    {
                        "label": key,
                        "role": role if role in ("spec", "content") else "field",
                        "children": array_children or None,
                    }
                )
            else:
                nodes.append(
                    {
                        "label": key,
                        "role": role,
                        "children": _build_detail_nodes(
                            value, role, child_path, project_url
                        ),
                    }
                )
            continue

        # Object value
        children = _build_detail_nodes(value, role, child_path, project_url)
        nodes.append(
            {
                "label": key,
                "role": role,
                "children": children or None,
            }
        )

    return nodes


def _populate_tree_node(tree_node: TreeNode, nodes: list[dict], depth: int = 0) -> None:
    """Recursively add node dicts to a Textual TreeNode."""
    for n in nodes:
        role = n.get("role", "field")
        label = n.get("label", "")
        value = n.get("value")
        can_make = n.get("can_make", False)

        if value is not None:
            markup = f"{_role_markup(label, role)}: {_role_markup(value, 'value')}"
        else:
            markup = _role_markup(label, role)

        if can_make and not n.get("children"):
            markup += " [dim][Make][/dim]"

        child_node = tree_node.add(markup, data=n, expand=(depth < 1))
        children = n.get("children") or []
        if children:
            _populate_tree_node(child_node, children, depth + 1)


def _build_library_tree_nodes(
    project_url: str, project: dict, info_data: dict
) -> list[dict]:
    """Build summary child nodes for the library tree (mirrors qtapp _build_tree_nodes)."""
    children: list[dict] = []

    for name in (project.get("contents") or {}).keys():
        children.append({"label": name, "role": "content", "project_url": project_url})

    for artifact_type, artifact_data in (project.get("artifacts") or {}).items():
        if isinstance(artifact_data, str):
            children.append(
                {
                    "label": artifact_type,
                    "role": "artifact",
                    "qname": artifact_type,
                    "project_url": project_url,
                    "can_make": True,
                }
            )
        elif isinstance(artifact_data, dict):
            for name in artifact_data.keys():
                children.append(
                    {
                        "label": f"{artifact_type}.{name}",
                        "role": "artifact",
                        "qname": f"{artifact_type}.{name}",
                        "project_url": project_url,
                        "can_make": True,
                    }
                )

    for spec_name, spec_data in (project.get("specs") or {}).items():
        spec_children: list[dict] = []
        for artifact_type, artifact_data in (spec_data.get("_artifacts") or {}).items():
            if isinstance(artifact_data, str):
                spec_children.append(
                    {
                        "label": artifact_type,
                        "role": "artifact",
                        "qname": f"{spec_name}.{artifact_type}",
                        "project_url": project_url,
                        "can_make": True,
                    }
                )
            elif isinstance(artifact_data, dict):
                for name in artifact_data.keys():
                    spec_children.append(
                        {
                            "label": f"{artifact_type}.{name}",
                            "role": "artifact",
                            "qname": f"{spec_name}.{artifact_type}.{name}",
                            "project_url": project_url,
                            "can_make": True,
                        }
                    )
        node: dict = {
            "label": spec_name,
            "role": "spec",
            "project_url": project_url,
        }
        if spec_children:
            node["children"] = spec_children
        children.append(node)

    return children


# ---------------------------------------------------------------------------
# Modal: create project
# ---------------------------------------------------------------------------


class CreateProjectModal(ModalScreen[str | None]):
    """Modal dialog to pick a project type to create."""

    DEFAULT_CSS = """
    CreateProjectModal {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 60;
        height: auto;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    #autocomplete {
        height: auto;
        max-height: 8;
        border: solid $primary-darken-2;
        display: none;
    }
    #autocomplete.visible {
        display: block;
    }
    #buttons {
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, spec_names: list[str]) -> None:
        super().__init__()
        self._spec_names = spec_names
        self._filtered: list[str] = list(spec_names)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Create Project — choose a type:")
            yield Input(placeholder="Type to filter…", id="type-input")
            yield ListView(id="autocomplete")
            with Horizontal(id="buttons"):
                yield Button("Create", variant="primary", id="btn-create")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._refresh_list("")
        self.query_one("#type-input", Input).focus()

    def _refresh_list(self, term: str) -> None:
        lv = self.query_one("#autocomplete", ListView)
        lv.clear()
        self._filtered = [s for s in self._spec_names if term.lower() in s.lower()]
        for name in self._filtered[:20]:
            lv.append(ListItem(Label(name)))
        if self._filtered:
            lv.add_class("visible")
        else:
            lv.remove_class("visible")

    @on(Input.Changed, "#type-input")
    def _on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_list(event.value)

    @on(ListView.Selected, "#autocomplete")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        lbl = event.item.query_one(Label)
        self.query_one("#type-input", Input).value = str(lbl.render())

    @on(Button.Pressed, "#btn-create")
    def _on_create(self) -> None:
        value = self.query_one("#type-input", Input).value.strip()
        self.dismiss(value or None)

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Modal: navigate to a path
# ---------------------------------------------------------------------------


class GoToPathModal(ModalScreen[str | None]):
    """Simple modal to type an arbitrary path."""

    DEFAULT_CSS = """
    GoToPathModal {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 70;
        height: auto;
    }
    #buttons {
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Navigate to path:")
            yield Input(value=self._current, id="path-input")
            with Horizontal(id="buttons"):
                yield Button("Go", variant="primary", id="btn-go")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        inp = self.query_one("#path-input", Input)
        inp.focus()

    @on(Button.Pressed, "#btn-go")
    def _on_go(self) -> None:
        value = self.query_one("#path-input", Input).value.strip()
        self.dismiss(value or None)

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

APP_CSS = """
Screen {
    background: #1e1e1e;
}

#left-pane {
    width: 1fr;
    border-right: solid #454545;
}

#centre-pane {
    width: 1fr;
    border-right: solid #454545;
}

#right-pane {
    width: 2fr;
}

#path-bar {
    height: 3;
    border-bottom: solid #454545;
    padding: 0 1;
    background: #252526;
}

#path-label {
    color: #9cdcfe;
    height: 3;
    content-align: left middle;
}

#fs-tree {
    background: #1e1e1e;
    scrollbar-color: #454545 #1e1e1e;
}

#lib-header {
    height: 3;
    border-bottom: solid #454545;
    padding: 0 1;
    background: #252526;
}

#lib-label {
    color: #dcb67a;
    height: 3;
    content-align: left middle;
}

#lib-tree {
    background: #1e1e1e;
    scrollbar-color: #454545 #1e1e1e;
}

#detail-header {
    height: auto;
    max-height: 5;
    border-bottom: solid #454545;
    padding: 0 1;
    background: #252526;
}

#detail-basename {
    color: #dcb67a;
    text-style: bold;
}

#detail-url {
    color: #9e9e9e;
}

#detail-tree {
    background: #1e1e1e;
    scrollbar-color: #454545 #1e1e1e;
}

#status-bar {
    height: 1;
    background: #007acc;
    color: white;
    padding: 0 1;
    dock: bottom;
}

Tree > .tree--guides {
    color: #454545;
}

Tree > .tree--guides-hover {
    color: #666666;
}

Tree > .tree--cursor {
    background: #094771;
    color: white;
}
"""


class ProjspecApp(App):
    """Projspec terminal browser — mirrors the QtApp three-pane layout."""

    TITLE = "Projspec Browser"
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home"),
        Binding("u", "go_up", "Up"),
        Binding("g", "goto_path", "Go to path"),
        Binding("s", "scan", "Scan"),
        Binding("c", "create_project", "Create"),
    ]

    current_path: reactive[str] = reactive(str(Path.home()), init=False)
    status_message: reactive[str] = reactive("Ready", init=False)

    # ── Init ─────────────────────────────────────────────────────────────────

    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        if path is None:
            path = str(Path.home())
        self._fs, self._path = fsspec.url_to_fs(path)
        self.current_path = path
        self._selected_project_url: str | None = None

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            # Left: filesystem tree
            with Vertical(id="left-pane"):
                with Horizontal(id="path-bar"):
                    yield Label("", id="path-label")
                yield Tree("", id="fs-tree")

            # Centre: library
            with Vertical(id="centre-pane"):
                with Horizontal(id="lib-header"):
                    yield Label("Library", id="lib-label")
                yield Tree("Projects", id="lib-tree")

            # Right: details
            with Vertical(id="right-pane"):
                with Vertical(id="detail-header"):
                    yield Label("", id="detail-basename")
                    yield Label("", id="detail-url")
                yield Tree("", id="detail-tree")

        yield Static("", id="status-bar")
        yield Footer()

    # ── Startup ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._refresh_path_label()
        self._populate_fs_tree()

    # ── Reactive watchers ─────────────────────────────────────────────────────

    def watch_current_path(self, path: str) -> None:
        self._refresh_path_label()
        self._populate_fs_tree()

    def watch_status_message(self, msg: str) -> None:
        try:
            self.query_one("#status-bar", Static).update(msg)
        except NoMatches:
            pass

    # ── Path helpers ──────────────────────────────────────────────────────────

    def _navigate(self, path: str) -> None:
        try:
            self._fs, _ = fsspec.url_to_fs(path)
        except Exception as e:
            self.status_message = f"Error: {e}"
            return
        self._path = path
        self.current_path = path

    def _refresh_path_label(self) -> None:
        try:
            self.query_one("#path-label", Label).update(self._path)
        except NoMatches:
            pass

    # ── Filesystem tree ───────────────────────────────────────────────────────

    def _populate_fs_tree(self) -> None:
        tree = self.query_one("#fs-tree", Tree)
        tree.clear()
        tree.root.set_label(self._path)
        tree.root.data = {
            "type": "directory",
            "name": self._path,
            "loaded": False,
        }
        self._load_fs_children(tree.root, self._path)
        tree.root.expand()

    def _load_fs_children(self, node: TreeNode, path: str) -> None:
        try:
            details = self._fs.ls(path, detail=True)
        except PermissionError:
            node.add_leaf("[red]Permission Denied[/red]")
            return
        except Exception as e:
            node.add_leaf(f"[red]Error: {e}[/red]")
            return

        items = sorted(
            details, key=lambda x: (x["type"] != "directory", x["name"].lower())
        )
        for item in items:
            name = item["name"].rsplit("/", 1)[-1]
            if name.startswith("."):
                continue
            if item["type"] == "directory":
                in_lib = (
                    item["name"] in library.entries
                    or self._fs.unstrip_protocol(item["name"]) in library.entries
                )
                icon = "📁" if not in_lib else "📋"
                child = node.add(f"{icon} {name}", data={**item, "loaded": False})
                # Add a placeholder so the expand arrow appears
                child.add_leaf("…")
            else:
                size = item.get("size")
                size_str = _format_size(size) if size is not None else ""
                node.add_leaf(
                    f"📄 {name}  [dim]{size_str}[/dim]",
                    data=item,
                )
        node.data = dict(node.data or {}, loaded=True)

    @on(Tree.NodeExpanded, "#fs-tree")
    def _on_fs_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        data = node.data or {}
        if data.get("type") == "directory" and not data.get("loaded"):
            # Remove placeholder
            node.remove_children()
            self._load_fs_children(node, data["name"])

    @on(Tree.NodeSelected, "#fs-tree")
    def _on_fs_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = node.data or {}
        if data.get("type") == "directory":
            path = self._fs.unstrip_protocol(data["name"])
            self._parse_and_add(path)

    @on(Tree.NodeHighlighted, "#fs-tree")
    def _on_fs_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        # Double-click-style navigation: pressing Enter on a dir navigates into it
        pass  # handled by action_go_into below via a separate key

    # ── Library tree ──────────────────────────────────────────────────────────

    def _refresh_library(self, scroll_to: str | None = None) -> None:
        tree = self.query_one("#lib-tree", Tree)
        tree.clear()

        info_data = class_infos()
        for project_url, proj in library.entries.items():
            proj_dict = proj.to_dict(compact=False)
            basename = project_url.split("/")[-1] or project_url
            project_node = tree.root.add(
                _role_markup(f"{basename}  [dim]{project_url}[/dim]", "project"),
                data={"project_url": project_url, "is_project": True},
                expand=False,
            )
            summary_nodes = _build_library_tree_nodes(project_url, proj_dict, info_data)
            _populate_tree_node(project_node, summary_nodes, depth=0)

        tree.root.expand()

    @on(Tree.NodeSelected, "#lib-tree")
    def _on_lib_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = node.data or {}
        project_url = data.get("project_url")
        if not project_url:
            return
        if data.get("is_project"):
            self._show_project_details(project_url)
        elif data.get("can_make") and data.get("qname"):
            # Pressing Enter on an artifact triggers make
            self._make_artifact(project_url, data["qname"])
        else:
            self._show_project_details(project_url)

    # ── Details tree ──────────────────────────────────────────────────────────

    def _show_project_details(self, project_url: str) -> None:
        proj = library.entries.get(project_url)
        if proj is None:
            return
        self._selected_project_url = project_url
        basename = project_url.split("/")[-1] or project_url

        try:
            self.query_one("#detail-basename", Label).update(
                _role_markup(basename, "project")
            )
            self.query_one("#detail-url", Label).update(f"[dim]{project_url}[/dim]")
        except NoMatches:
            pass

        detail_tree = self.query_one("#detail-tree", Tree)
        detail_tree.clear()
        detail_tree.root.set_label(_role_markup(basename, "project"))

        proj_dict = proj.to_dict(compact=False)
        nodes = _build_detail_nodes(proj_dict, "none", "", project_url)
        _populate_tree_node(detail_tree.root, nodes, depth=0)
        detail_tree.root.expand()

    @on(Tree.NodeSelected, "#detail-tree")
    def _on_detail_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = node.data or {}
        if data.get("can_make") and data.get("qname") and data.get("project_url"):
            self._make_artifact(data["project_url"], data["qname"])

    # ── Parse / add project ───────────────────────────────────────────────────

    def _parse_and_add(self, path: str) -> None:
        self.status_message = f"Parsing {path}…"
        try:
            proj = projspec.Project(path, walk=False, fs=self._fs)
        except Exception as e:
            self.status_message = f"Parse error: {e}"
            return
        if proj.specs:
            library.add_entry(path, proj)
            self._refresh_library(scroll_to=path)
            self._show_project_details(path)
            self.status_message = f"Added: {path}"
        else:
            self.status_message = f"No specs found in {path}"

    # ── Artifact make ─────────────────────────────────────────────────────────

    def _make_artifact(self, project_url: str, qname: str) -> None:
        proj = library.entries.get(project_url)
        if proj is None:
            self.status_message = f"Project not found: {project_url}"
            return
        self.status_message = f"Making {qname} in {project_url}…"
        try:
            art = proj.make(qname)
            self.status_message = f"Done: {art}"
        except Exception as e:
            self.status_message = f"Make failed: {e}"

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_go_home(self) -> None:
        self._navigate(str(Path.home()))

    def action_go_up(self) -> None:
        stripped = str(self._fs._strip_protocol(self._path))
        parent = posixpath.dirname(stripped.rstrip("/"))
        if not parent or parent == stripped:
            return
        self._navigate(self._fs.unstrip_protocol(parent))

    def action_goto_path(self) -> None:
        def _callback(result: str | None) -> None:
            if result:
                self._navigate(result)

        self.push_screen(GoToPathModal(self._path), _callback)

    def action_scan(self) -> None:
        self.status_message = f"Scanning {self._path}…"
        try:
            proj = projspec.Project(self._path, walk=True, fs=self._fs)
            for url, child in proj.children.items():
                if child.specs:
                    library.add_entry(url, child)
            if proj.specs:
                library.add_entry(self._path, proj)
            self._refresh_library(scroll_to=self._path)
            self.status_message = f"Scan complete: {self._path}"
        except Exception as e:
            self.status_message = f"Scan failed: {e}"

    def action_create_project(self) -> None:
        info_data = class_infos()
        spec_names = list(info_data.get("specs", {}).keys())

        def _callback(project_type: str | None) -> None:
            if not project_type:
                return
            try:
                proj = projspec.Project(self._path, walk=False, fs=self._fs)
                proj.create(project_type)
                library.add_entry(self._path, proj)
                self._refresh_library(scroll_to=self._path)
                self.status_message = f"Created {project_type} in {self._path}"
            except Exception as e:
                self.status_message = f"Create failed: {e}"

        self.push_screen(CreateProjectModal(spec_names), _callback)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_size(size: int | None) -> str:
    if size is None:
        return ""
    sz: float = size
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if sz < 1024.0:
            return f"{sz:.1f} {unit}"
        sz /= 1024.0
    return f"{sz:.1f} PB"
    return f"{size:.1f} PB"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    app = ProjspecApp(path=path)
    app.run()


if __name__ == "__main__":
    main()
