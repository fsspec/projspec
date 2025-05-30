from functools import cached_property
import toml

from projspec.utils import AttrDict, camel_to_snake

import fsspec

registry = set()


class Project:

    def __init__(self, path, storage_options=None, fs=None, walk=None):
        if fs is None:
            fs, path = fsspec.url_to_fs(path, storage_options=storage_options)
        self.fs = fs
        self.url = path
        self.specs = {}
        self.children = {}
        self.resolve(walk=walk)

    def resolve(self, subpath: str = "", walk: bool | None = None) -> None:
        """Fill out project specs in this directory

        :param subpath: find specs at the given subpath
        :param walk: if None (default) only try subdirectories if root has
            no specs, and don't descend further. If True, recurse all directories;
            if False don't descend at all.
        """
        fullpath = "/".join([self.url, subpath]) if subpath else self.url
        for cls in registry:
            try:
                self.specs[camel_to_snake(cls.__name__)] = cls(self)
            except ValueError as e:
                pass
        if walk or (walk is None and not self.specs):
            for fileinfo in self.fs.ls(fullpath, detail=True):
                if fileinfo["type"] == "directory":
                    sub = f"{subpath}/{fileinfo["name"].rsplit("/", 1)[-1]}"
                    proj2 = Project(fileinfo["name"], fs=self.fs,
                                                 walk=walk or False)
                    if proj2.specs:
                        self.children[sub] = proj2
                    elif proj2.children:
                        self.children.update({f"{sub}/{s2}": p for s2, p in proj2.children.items()})


    @cached_property
    def filelist(self):
        return self.fs.ls(self.url)

    def __repr__(self):
        # TODO: show children, adding indents
        return (f"<Project '{self.url}'>\n"
                f"\n{'\n\n'.join(f"{_}" for _ in self.specs.values())}")

    @cached_property
    def pyproject(self):
        """Contents of top-level pyproject.toml, if found"""
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in self.filelist}
        if "pyproject.toml" in basenames:
            try:
                with self.fs.open(basenames["pyproject.toml"], "rt") as f:
                    return toml.load(f)
            except (IOError, ValueError, TypeError):
                # debug/warn?
                pass
        return {}


class ProjectSpec:
    """A project specification

    Also provides fallback from pyproject.toml standard layout without additional
    runtime specification (uv, pixi, maturin, etc.).
    """

    def __init__(self, root: Project, subpath: str = ""):
        self.root = root
        self.subpath = subpath  # not used yet
        self._contents = None
        self._artifacts = None
        if not self.match():
            raise ValueError(f"Not a {type(self).__name__}")

    @property
    def path(self) -> str:
        """Location of this project spec"""
        return self.root.url + "/" + self.subpath if self.subpath else self.root.url

    def match(self) -> bool:
        """Whether the given path can be interpreted as this type of project"""
        raise NotImplementedError

    @property
    def contents(self) -> AttrDict:
        """A mapping of types and in each a list of objects from this project

        Contents means the things that are within a project as part of its description,
        see ``projspec.content``.
        """
        if self._contents is None:
            self.parse()
        return self._contents

    @property
    def artifacts(self) -> AttrDict:
        """A mapping of types and in each a list of objects from this project

        Artifacts are things a project can make/do. See ``projspec.artifact``.
        """
        if self._artifacts is None:
            self.parse()
        return self._artifacts

    def parse(self) -> None:
        # TODO: returns known children
        raise NotImplementedError

    def clean(self) -> None:
        """Remove any artifacts and runtimes produced by this project"""
        for artgroup in self.artifacts.values():
            for art in artgroup.values():
                art.clean(True)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        registry.add(cls)

    def __repr__(self):
        return (f"<{type(self).__name__}>\nContents:\n {self.contents}\n"
                f"Artifacts:\n {self.artifacts}")
