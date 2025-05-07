from abc import ABC
from functools import cached_property

from projspec.utils import AttrDict

import fsspec

registry = set()


class ProjectSpec(ABC):

    def __init__(self, path: str, storage_options: dict | None = None):
        fs, url = fsspec.url_to_fs(path, **(storage_options or {}))
        self.url: str = url
        self.fs: fsspec.AbstractFileSystem = fs

    @staticmethod
    def match(path: str,  storage_options: dict | None = None) -> bool:
        """Whether the given path can be interpreted as this type of project"""
        raise NotImplementedError

    @cached_property
    def contents(self) -> AttrDict:
        """A mapping of types and in each a list of objects from this project

        Contents means the things that are within a project as part of its description,
        see ``projspec.content``.
        """
        raise NotImplementedError

    @cached_property
    def artifacts(self) -> AttrDict:
        """A mapping of types and in each a list of objects from this project

        Artifacts are things a project can make/do. See ``projspec.artifact``.
        """
        raise NotImplementedError

    @classmethod
    def __subclasshook__(cls, __subclass):
        registry.add(__subclass)
