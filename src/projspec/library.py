import json
import os

import fsspec

from projspec.config import get_conf
from projspec.proj import Project


class ProjectLibrary:
    """Stores scanned project objects at a given path in JSON format

    An instance of this library ``library`` is created on import.

    In the future, alternative serialisations will be implemented.
    """

    # TODO: support for remote libraries

    def __init__(self, library_path: str | None = None, auto_save: bool = True):
        self.path = library_path or get_conf("library_path")
        self.load()
        self.entries: dict[str, Project] = {}
        self.auto_save = auto_save

    def load(self):
        """Loads scanned project objects from JSON file"""
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
        data = {k: v.to_dict(compact=False) for k, v in self.entries.items()}
        with fsspec.open(self.path, "w") as f:
            json.dump(data, f)

    def filter(self, filters: list[tuple[str, str]]) -> dict[str, Project]:
        return {k: v for k, v in self.entries.items() if _match(v, filters)}


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


library = ProjectLibrary()
library.load()
