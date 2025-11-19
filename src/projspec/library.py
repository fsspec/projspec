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
        self.entries = {}
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


library = ProjectLibrary()
library.load()
