import io
import logging
from collections.abc import Iterable
from itertools import chain
from functools import cached_property

import fsspec
import fsspec.implementations.local
import toml

from projspec.config import get_conf
from projspec.utils import (
    AttrDict,
    IndentDumper,
    PickleableTomlDecoder,
    camel_to_snake,
    get_cls,
    flatten,
)

logger = logging.getLogger("projspec")
registry = {}

# we don't consider these as possible child projects when walk=True
default_excludes = {
    # TODO: make this a conf
    # TODO: add more here
    # we always ignore directories starting with "." or "_"
    "bld",
    "build",
    "dist",
    "env",
    "envs",  # conda-project
    "htmlcov",
}


class ParseFailed(ValueError):
    """Exception raised when parsing fails: a directory does not meet the given spec."""


class Project:
    """Top level representation of a project directory

    This holds any parsed project metadata specs, top level contents and artifacts and
    any project details from nested child directories.
    """

    def __init__(
        self,
        path: str,
        storage_options: dict | None = None,
        fs: fsspec.AbstractFileSystem | None = None,
        # TODO: allow int for walk, for set number of levels; combine with preloading files
        walk: bool | None = None,
        types: set[str] | None = None,
        xtypes: set[str] | None = None,
        excludes: set[str] | None = None,
    ):
        """

        :param path: URL location of the project directory root
        :param storage_options: any arguments to pass to fsspec to access the files
        :param fs: if given, use this fsspec-compatible filesystem
        :param walk: if True, unconditionally descend into child directories and attempt
            to parse them. If False, never descend. If None (default), descend only in
            the case that the root did not many any project type.
        :param types: only allow specs whose names are included.
        :param xtypes: disallow specs whose names are in this set
        :param excludes: directory names to ignore. If None, uses default_excludes.
        """
        self.path = path
        if fs is None:
            fs, path = fsspec.url_to_fs(path, **(storage_options or {}))
        else:
            storage_options = fs.storage_options
        self.storage_options = storage_options or {}
        self.fs = fs
        self.url = path  # this is the FS-specific variant
        self.specs = AttrDict()
        self.children = AttrDict()
        self.contents = AttrDict()
        self.artifacts = AttrDict()
        # read and respect .gitignore? for exclude directories?
        self.excludes = excludes or default_excludes
        self._pyproject = None
        self._scanned_files = None
        self.resolve(walk=walk, types=types, xtypes=xtypes)
        # clear cached files
        self._scanned_files = None

    def is_local(self) -> bool:
        """Did we read this from the local filesystem?"""
        # see also fsspec.utils.can_be_local for more flexibility with caching.
        return isinstance(self.fs, fsspec.implementations.local.LocalFileSystem)

    @property
    def scanned_files(self):
        if self._scanned_files is None:
            types = get_conf("scan_types")
            if not types:
                return {}
            size = get_conf("scan_max_size")
            allfiles = [
                _
                for _ in self.filelist
                if _["name"].endswith(tuple(types)) and _["size"] < size
            ]
            if len(allfiles) > get_conf("scan_max_files"):
                logger.debug(
                    "Skipping scanning of %d files in %s",
                    len(allfiles),
                    self.url,
                )
                return {}
            self._scanned_files = {
                k.rsplit("/", 1)[-1]: v
                for k, v in self.fs.cat([_["name"] for _ in allfiles]).items()
            }
        return self._scanned_files

    def get_file(self, name: str, text=True) -> io.IOBase:
        if name in self.scanned_files:
            if text:
                return io.StringIO(self.scanned_files[name].decode())
            return io.BytesIO(self.scanned_files[name])
        return self.fs.open(f"{self.url}/{name}", mode="rt" if text else "rb")

    def resolve(
        self,
        walk: bool | None = None,
        types: set[str] | None = None,
        xtypes: set[str] | None = None,
    ) -> None:
        """Fill out project specs in this directory

        :param walk: if None (default) only try subdirectories if root has
            no specs, and don't descend further. If True, recurse all directories;
            if False, don't descend at all.
        :param types: names of types to allow while parsing. If empty or None, allow all
        :param xtypes: names of types to disallow while parsing.
        """
        if types and set(types) - set(registry):
            raise ValueError(f"Unknown types: {set(types) - set(registry)}")
        # sorting to ensure consistency
        for name in sorted(registry):
            cls = registry[name]
            try:
                name = cls.__name__
                snake_name = camel_to_snake(cls.__name__)
                if (types and {name, snake_name}.isdisjoint(types)) or {
                    name,
                    snake_name,
                }.intersection(xtypes or set()):
                    continue
                logger.debug("resolving %s as %s", self.url, cls)
                inst = cls(self)
                inst.parse()
                if isinstance(inst, ProjectExtra):
                    self.contents.update(inst.contents)
                    self.artifacts.update(inst.artifacts)
                else:
                    self.specs[snake_name] = inst
            except ValueError:
                logger.debug("failed")
            except Exception as e:
                # we don't want to fail the parse completely
                logger.exception("Failed to resolve spec %r", e)
        if walk or (walk is None and not self.specs):
            for fileinfo in self.filelist:
                if fileinfo["type"] == "directory":
                    # TODO: some types (like python packages) are recursive; so we should
                    #  separate out the parse and children steps, and only descend to
                    #  children if no recursive types match
                    # Alternatively: allow walk to be an integer, indicating the depth
                    #  of search.
                    basename = fileinfo["name"].rsplit("/", 1)[-1]
                    if basename in self.excludes or basename.startswith((".", "_")):
                        continue
                    proj2 = Project(
                        fileinfo["name"],
                        fs=self.fs,
                        walk=walk or False,
                        types=types,
                        xtypes=xtypes,
                        excludes=self.excludes,
                    )
                    if proj2.specs:
                        self.children[basename] = proj2
                    elif proj2.children:
                        self.children.update(
                            {
                                f"{basename.rstrip('/')}/{s2.lstrip('/')}": p
                                for s2, p in proj2.children.items()
                            }
                        )

    @cached_property
    def filelist(self):
        return self.fs.ls(self.url, detail=True)

    @cached_property
    def basenames(self):
        return {_["name"].rsplit("/", 1)[-1]: _["name"] for _ in self.filelist}

    def text_summary(self) -> str:
        """Only shows project types, not what they contain"""
        txt = f"<Project '{self.fs.unstrip_protocol(self.url)}'>\n"
        bits = [
            f" {'/'}: {' '.join(type(_).__name__ for _ in chain(self.specs.values(), self.contents.values(), self.artifacts.values()))}"
        ] + [
            f" {k}: {' '.join(type(_).__name__ for _ in v.specs.values())}"
            for k, v in self.children.items()
        ]
        return txt + "\n".join(bits)

    def __repr__(self):
        txt = "<Project '{}'>\n\n{}".format(
            self.fs.unstrip_protocol(self.url),
            "\n\n".join(str(_) for _ in self.specs.values()),
        )
        if self.contents or self.artifacts:
            txt += "\n\n<GLOBAL>\n"
        if self.contents:
            ch = "\n".join([f" {k}: {v}" for k, v in self.contents.items()])
            txt += f"\nContents:\n{ch}"
        if self.artifacts:
            ch = "\n".join([f" {k}: {v}" for k, v in self.artifacts.items()])
            txt += f"\nArtifacts:\n{ch}"
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
        try:
            with self.get_file("pyproject.toml") as f:
                return toml.load(f, decoder=PickleableTomlDecoder())
        except (OSError, ValueError, TypeError):
            # debug/warn?
            pass
        return {}

    def all_artifacts(self, names: str | None = None) -> list:
        """A flat list of all the artifact objects nested in this project."""
        arts = set(self.artifacts.values())
        for spec in self.specs.values():
            arts.update(flatten(spec.artifacts))
        for child in self.children.values():
            arts.update(child.artifacts)
        arts.update(self.artifacts.values())
        if names:
            if isinstance(names, str):
                names = {names}
            arts = [
                a
                for a in arts
                if any(a.snake_name() == camel_to_snake(n) for n in names)
            ]
        else:
            arts = list(arts)
        return arts

    def has_artifact_type(self, types: Iterable[type]) -> bool:
        """Answers 'does this project support outputting the given artifact type'

        This is an experimental example of filtering through projects
        """
        types = tuple(types)
        return any(isinstance(_, types) for _ in self.all_artifacts())

    def all_contents(self, names=None) -> list:
        """A flat list of all the content objects nested in this project."""
        # TODO: deduplicate these non-hashables
        cont = list(self.contents.values())
        for spec in self.specs.values():
            cont.extend(flatten(spec.contents))
        for child in self.children.values():
            cont.extend(child.all_contents(names=names))
        cont.extend(self.contents.values())
        if names:
            if isinstance(names, str):
                names = {names}
            cont = [
                a
                for a in cont
                if any(a.snake_name() == camel_to_snake(n) for n in names)
            ]
        else:
            cont = list(cont)
        return cont

    def has_content_type(self, types: Iterable[type]) -> bool:
        """Answers 'does this project support outputting the given content type'

        This is an experimental example of filtering through projects
        """
        types = tuple(types)
        return any(isinstance(_, types) for _ in self.all_contents())

    def __contains__(self, item) -> bool:
        """Is the given project type supported ANYWHERE in this directory?"""
        item = camel_to_snake(item)
        return item in self.specs or any(item in _ for _ in self.children.values())

    def to_dict(self, compact=True) -> dict:
        dic = AttrDict(
            specs=self.specs,
            children=self.children,
            url=self.path,
            storage_options=self.storage_options,
            artifacts=self.artifacts,
            contents=self.contents,
        )
        if not compact:
            dic["klass"] = "project"
        return dic.to_dict(compact=compact)

    def _repr_html_(self):
        from projspec.html import dict_to_html

        # TODO: add tooltips to docs or spec links
        # TODO: remove redundant information?
        return dict_to_html(self.to_dict(), title=self.url)

    @staticmethod
    def from_dict(dic):
        from projspec.utils import from_dict

        if not dic.get("klass", "") == "project":
            raise ValueError("Not a project dict")
        proj = object.__new__(Project)
        proj.specs = from_dict(dic["specs"], proj)
        proj.children = from_dict(dic["children"], proj)
        proj.contents = from_dict(dic["contents"], proj)
        proj.artifacts = from_dict(dic["artifacts"], proj)
        proj.path = dic["url"]
        proj.storage_options = dic["storage_options"]
        proj.fs, proj.url = fsspec.url_to_fs(proj.path, **proj.storage_options)
        return proj

    def create(self, name: str):
        """Make this project conform to the given project spec type."""
        cls = get_cls(name)
        # causes reparse and makes a new instance
        # could rerun resolve or only parse for give type and add, instead.
        return cls.create(self.path)


class ProjectSpec:
    """A project specification

    Subclasses of this define particular project types, and if a project conforms to
    the given type, then parsing it with the class will succeed and the contents and
    artifacts will be populated.

    Checking if a path _might_ meet a spec (with .match()) should be cheap, and
    parsing (with .parse()) should normally only require reading a few text files of metadata.

    Subclasses are automatically added to the registry on import, and any Project will
    attempt to parse its given path with every class (which is why making .match() fast
    is important).
    """

    spec_doc = ""  # URL to prose about this spec

    def __init__(self, proj: Project):
        self.proj = proj
        self._contents = AttrDict()
        self._artifacts = AttrDict()
        if not self.match():
            raise ParseFailed(f"Not a {type(self).__name__}")

    def match(self) -> bool:
        """Whether the given path might be interpreted as this type of project"""
        # should be fast, not require a full parse, which we will probably do right after
        # may store attributes to be used later in parse()
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

    @staticmethod
    def _create(path: str) -> None:
        raise NotImplementedError("Subclass must implement this")

    @classmethod
    def create(cls, path: str) -> Project:
        """Make the target directory compliant with this project type, if not already"""
        # TODO: implement remote??
        # TODO: implement dry-run?
        import os.path

        os.makedirs(path, exist_ok=True)
        if not cls.snake_name() in Project(path):
            cls._create(path)
        # perhaps should return ProjSpec, but it needs to be added to a project
        return Project(path)

    def parse(self) -> None:
        raise ParseFailed

    def clean(self) -> None:
        """Remove any artifacts and runtimes produced by this project"""
        for artgroup in self.artifacts.values():
            for art in artgroup.values():
                art.clean(True)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        registry[camel_to_snake(cls.__name__)] = cls

    def __repr__(self):
        import yaml

        base = f"<{type(self).__name__}>"
        if self.contents:
            base += f"\nContents:\n{yaml.dump(self.contents.to_dict(), Dumper=IndentDumper).rstrip()}\n"
        if self.artifacts:
            base += f"\nArtifacts:\n{yaml.dump(self.artifacts.to_dict(), Dumper=IndentDumper).rstrip()}\n"
        return base

    def to_dict(self, compact=True) -> dict:
        dic = AttrDict(
            _contents=self.contents,
            _artifacts=self.artifacts,
        )
        if not compact:
            dic["klass"] = ["projspec", self.snake_name()]
        return dic.to_dict(compact=compact)

    def get_file(self, name: str, text=True) -> io.IOBase:
        return self.proj.get_file(name, text=text)

    @classmethod
    def snake_name(cls) -> str:
        """Convert a project name to snake-case"""
        return camel_to_snake(cls.__name__)


class ProjectExtra(ProjectSpec):
    """A special subcategory of project types with content but no structure.

    Subclasses of this are special: they are not free standing projects, but add
    contents onto the root project. Examples include data catalog specification, linters
    and CI/CD, that may be run against the root project without using a project-oriented
    tool.

    These classes do not appear in a Project's .specs, but do contribute .contents or
    .artifacts. They are still referenced when filtering spec types by name.

    Commonly, subclasses are tied 1-1 to a particular content/artifact class.
    """
