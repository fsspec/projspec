import logging
from collections.abc import Iterable
from functools import cached_property

import fsspec
import fsspec.implementations.local
import toml

from projspec.utils import AttrDict, IndentDumper, camel_to_snake, flatten

logger = logging.getLogger("projspec")
registry = set()
default_excludes = {
    ".venv",  # venv, pipenv, uv
    ".pixi",
    "envs",  # conda-project
    "bld",
    ".git",
    "distbuild",
}


class Project:
    def __init__(
        self,
        path: str,
        storage_options: dict | None = None,
        fs: fsspec.AbstractFileSystem | None = None,
        walk: bool | None = None,
        types: set[str] | None = None,
        excludes: set[str] | None = None,
    ):
        if fs is None:
            fs, path = fsspec.url_to_fs(path, **(storage_options or {}))
        self.fs = fs
        self.url = path
        self.specs = {}
        self.children = {}
        self.excludes = excludes or default_excludes
        self.resolve(walk=walk, types=types)

    def is_local(self) -> bool:
        """Did we read this from the local filesystem"""
        # see also fsspec.utils.can_be_local for more flexibility with caching.
        return isinstance(self.fs, fsspec.implementations.local.LocalFileSystem)

    def resolve(
        self,
        subpath: str = "",
        walk: bool | None = None,
        types: set[str] | None = None,
    ) -> None:
        """Fill out project specs in this directory

        :param subpath: find specs at the given subpath
        :param walk: if None (default) only try subdirectories if root has
            no specs, and don't descend further. If True, recurse all directories;
            if False don't descend at all.
        :param types: names of types to allow while parsing. If empty or None, allow all
        """
        fullpath = "/".join([self.url, subpath]) if subpath else self.url
        # sorting to ensure consistency
        for cls in sorted(registry, key=str):
            try:
                logger.debug("resolving %s as %s", fullpath, cls)
                name = cls.__name__
                snake_name = camel_to_snake(cls.__name__)
                if types and name not in types and snake_name not in types:
                    # TODO: allow partial matches here
                    continue
                inst = cls(self)
                inst.parse()
                self.specs[snake_name] = inst
            except ValueError:
                logger.debug("failed")
            except Exception as e:
                # we don't want to fail the parse completely
                logger.exception("Failed to resolve spec %r", e)
                continue
        if walk or (walk is None and not self.specs):
            for fileinfo in self.fs.ls(fullpath, detail=True):
                if fileinfo["type"] == "directory":
                    basename = fileinfo["name"].rsplit("/", 1)[-1]
                    if basename in self.excludes:
                        continue
                    sub = f"{subpath}/{basename}"
                    proj2 = Project(
                        fileinfo["name"],
                        fs=self.fs,
                        walk=walk or False,
                        types=types,
                        excludes=self.excludes,
                    )
                    if proj2.specs:
                        self.children[sub] = proj2
                    elif proj2.children:
                        self.children.update(
                            {
                                f"{sub.rstrip('/')}/{s2.lstrip('/')}": p
                                for s2, p in proj2.children.items()
                            }
                        )

    @cached_property
    def filelist(self):
        return self.fs.ls(self.url, detail=False)

    @cached_property
    def basenames(self):
        return {_.rsplit("/", 1)[-1]: _ for _ in self.filelist}

    def __repr__(self):
        txt = "<Project '{}'>\n\n{}".format(
            self.fs.unstrip_protocol(self.url),
            "\n\n".join(str(_) for _ in self.specs.values()),
        )
        if self.children:
            ch = "\n".join(
                [
                    f" {k}: {' '.join(type(_).__name__ for _ in v.specs.values())}"
                    for k, v in self.children.items()
                ]
            )
            txt += f"\n\nChildren:\n{ch}"
        return txt

    def __getitem__(self, key):
        if key in self.specs:
            return self.specs[key]
        elif key in self.children:
            return self.children[key]
        raise KeyError(key)

    def __getattr__(self, key):
        if key in self.specs:
            return self.specs[key]
        raise AttributeError(key)

    @cached_property
    def pyproject(self):
        """Contents of top-level pyproject.toml, if found"""
        if "pyproject.toml" in self.basenames:
            try:
                with self.fs.open(self.basenames["pyproject.toml"], "rt") as f:
                    return toml.load(f)
            except (OSError, ValueError, TypeError):
                # debug/warn?
                pass
        return {}

    @property
    def artifacts(self) -> set:
        """A flat list of all the artifact objects nested in this project."""
        arts = set()
        for spec in self.specs.values():
            arts.update(flatten(spec.artifacts))
        for child in self.children.values():
            arts.update(child.artifacts)
        return arts

    def filter_by_type(self, types: Iterable[type]) -> bool:
        """Answers 'does this project support outputting the given artifact type'

        This is an experimental example of filtering through projects
        """
        types = tuple(types)
        return any(isinstance(_, types) for _ in self.artifacts)

    def __contains__(self, item) -> bool:
        """Is the given project type supported ANYWHERE in this directory?"""
        return item in self.specs or any(
            item in _ for _ in self.children.values()
        )


class ProjectSpec:
    """A project specification

    Also provides fallback from pyproject.toml standard layout without additional
    runtime specification (uv, pixi, maturin, etc.).
    """

    spec_doc = ""  # URL to prose about this spec

    def __init__(self, root: Project, subpath: str = ""):
        self.root = root
        self.subpath = subpath  # not used yet
        self._contents = AttrDict()
        self._artifacts = AttrDict()
        if not self.match():
            raise ValueError(f"Not a {type(self).__name__}")

    @property
    def path(self) -> str:
        """Location of this project spec"""
        return (
            self.root.url + "/" + self.subpath
            if self.subpath
            else self.root.url
        )

    def match(self) -> bool:
        """Whether the given path might be interpreted as this type of project"""
        # should be fast, not require a full parse, which we will probably do right after
        return False

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
        # should raise ValueError if the project cannot be interpreted as this type
        raise ValueError

    def clean(self) -> None:
        """Remove any artifacts and runtimes produced by this project"""
        for artgroup in self.artifacts.values():
            for art in artgroup.values():
                art.clean(True)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        registry.add(cls)

    def __repr__(self):
        import yaml

        base = f"<{type(self).__name__}>"
        if self.contents:
            base += f"\nContents:\n{yaml.dump(self.contents.to_dict(), Dumper=IndentDumper).rstrip()}\n"
        if self.artifacts:
            base += f"\nArtifacts:\n{yaml.dump(self.artifacts.to_dict(), Dumper=IndentDumper).rstrip()}\n"
        return base
