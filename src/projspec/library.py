import json
import os

import fsspec

from projspec.config import get_conf
from projspec.proj import Project
from projspec.utils import DEFAULT


class ProjectLibrary:
    """Stores scanned project objects at a given path in JSON format

    In the future, alternative serialisations will be implemented.
    """

    # TODO: support for remote libraries

    def __init__(
        self,
        library_path: str | None | type = DEFAULT,
        auto_save: bool = True,
        entries: dict | None = None,
    ):
        self.path = (
            get_conf("library_path") if library_path is DEFAULT else library_path
        )
        self.entries: dict[str, Project] = {} if entries is None else entries
        self.auto_save = auto_save
        self.load()

    def load(self):
        """Loads scanned project objects from JSON file"""
        if self.path is None:
            return
        try:
            with fsspec.open(self.path, "r") as f:
                self.entries = {
                    k: Project.from_dict(v) for k, v in json.load(f).items()
                }
        except FileNotFoundError:
            self.entries = {}

    def clear(self):
        """Clears scanned project objects from JSON file and memory"""
        if os.path.isfile(self.path):
            os.unlink(self.path)
        self.entries = {}

    def add_entry(self, path: str, entry: Project):
        """Adds an entry to the scanned project object"""
        self.entries[path] = entry
        if self.auto_save:
            self.save()

    def save(self):
        """Serialise the state of the scanned project objects to file"""
        # don't catch
        if self.path is None:
            raise ValueError("Cannot save without .path set")
        data = {k: v.to_dict(compact=False) for k, v in self.entries.items()}
        with fsspec.open(self.path, "w") as f:
            json.dump(data, f)

    def filter(self, filters: list[tuple[str, str]]) -> dict[str, Project]:
        return {k: v for k, v in self.entries.items() if _match(v, filters)}

    # ------------------------------------------------------------------
    #  Rich display / ipywidget
    # ------------------------------------------------------------------
    def ipywidget(self):
        """Return an interactive Jupyter widget for this library.

        The widget mirrors the two-pane UI used by the VSCode extension,
        the Qt app and the PyCharm plugin: a filterable project list on
        the left and a details panel on the right, with chips for each
        spec, Content and Artifact grouping, a kebab menu for per-project
        actions (rescan, create spec, remove from library, …) and per-
        artifact Make buttons.

        Requires the optional ``anywidget`` and ``ipywidgets`` packages;
        install them via ``pip install projspec[ipywidget]``.

        Only a single widget per notebook is supported - see the
        :mod:`projspec.webui.ipywidget` module docstring.
        """
        from projspec.webui.ipywidget import make_widget

        return make_widget(self)

    def _ipython_display_(self):
        """Auto-display as the interactive widget when possible.

        Falls back to a plain ``repr`` when ``anywidget`` /
        ``ipywidgets`` is not available - Jupyter will then use the
        normal text representation.
        """
        try:
            widget = self.ipywidget()
        except ImportError:
            # No optional deps; let Jupyter fall back to repr().
            print(repr(self))
            return
        from IPython.display import display

        display(widget)


# move to Project definition?
def _match(proj: Project, filters: list[tuple[str, str | tuple[str]]]) -> bool:
    # TODO: this is all AND, but you can get OR by passing a tuple of values
    for cat, value in filters:
        # TODO: make categories an enum
        if cat == "spec" and value not in proj:
            return False
        if cat == "artifact" and not proj.all_artifacts(value):
            return False
        if cat == "content" and not proj.all_contents(value):
            return False
    return True
