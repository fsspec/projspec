from functools import cached_property
import toml

from projspec.utils import AttrDict, camel_to_snake

import fsspec

registry = set()


class Project:

    def __init__(self, path, storage_options=None):
        fs, url = fsspec.url_to_fs(path, storage_options=storage_options)
        self.fs = fs
        self.url = url
        self.specs = {}
        self.resolve()

    def resolve(self):
        # TODO: walk directory tree with reasonable stops
        #  maybe as subprojects of each Spec.
        for cls in registry:
            try:
                self.specs[camel_to_snake(cls.__name__)] = cls(self)
            except ValueError as e:
                print(cls, e)
                pass

    @cached_property
    def filelist(self):
        return self.fs.ls(self.url)

    def __repr__(self):
        return (f"<Project '{self.url}'>\n"
                f"\n{'\n'.join(str(_) for _ in self.specs.values())}")

    @cached_property
    def pyproject(self):
        """Contents of top-level pyproject.toml, if found"""
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in self.filelist}
        if "pyproject.toml" in basenames:
            try:
                with self.fs.open(basenames["pyproject.toml"], "rt") as f:
                    return toml.load(f)
            except (IOError, ValueError, TypeError):
                # debug/warn
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
        if not self.match():
            raise ValueError(f"Not a {type(self).__name__}")

    @property
    def path(self) -> str:
        return self.root.url + "/" + self.subpath if self.subpath else self.root.url

    def match(self) -> bool:
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

    def clean(self):
        """Remove any artifacts and runtimes produced by this project"""
        for artgroup in self.artifacts.values():
            for art in artgroup.values():
                art.clean(True)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        registry.add(cls)

    def __repr__(self):
        return (f"<{type(self).__name__}>\nContents: {self.contents}\n"
                f"Artifacts: {self.artifacts}")
