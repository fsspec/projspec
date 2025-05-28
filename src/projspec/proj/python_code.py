from typing import Type
from functools import cached_property


import fsspec

from projspec.utils import AttrDict
from projspec.proj.base import ProjectSpec


class PythonCode(ProjectSpec):
    """Code directly importable by python

    This applies to isolated .py files and directories with __init__.py.

    Such a structure does not declare any envs, deps, etc. It contains
    nothing interesting _except_ code.

    We assume a free-floating py file is executable if it has x permissions or "#!";
    could introspect for a ``__main__`` annotation. A package is executable if
    it contains a ``__main__.py`` file - but of course
    """
    def match(self) -> bool:
        basenames = set(_.rsplit("/", 1)[-1] for _ in self.root.filelist)
        return "__init__.py" in basenames

    def parse(self):
        from projspec.content.package import PythonPackage
        from projspec.content.executable import Command
        from projspec.artifact.process import Process

        arts = AttrDict()
        exe = [_ for _ in self.root.filelist if _.rsplit("/", 1)[-1] == "__main__.py"]
        if exe:
            arts["process"] = AttrDict(main=Process(proj=self.root, cmd=["python", exe[0]]))
        self._artifacts = arts
        out = AttrDict(PythonPackage(proj=self.root, artifacts=set(), package_name=self.path.rsplit("/", 1)[-1]))
        if arts:
            art = arts["process"]["main"]
            out["command"] = AttrDict(main=Command(proj=self.root, artifacts={art}, args=art.cmd))
        self._contents = out


class PythonLibrary(ProjectSpec):
    """Complete python buildable project

    Defined by existence of pyproject.toml or setup.py.
    """
    def match(self) -> bool:
        basenames = set(_.rsplit("/", 1)[-1] for _ in self.root.filelist)
        return "pyproject.toml" in basenames or "setup.py" in basenames

    def parse(self):
        from projspec.artifact.installable import Wheel
        from projspec.content.package import PythonPackage
        if "build-system" in self.root.pyproject:
            # should imply that "python -m build" can run
            self._artifacts = AttrDict(Wheel(proj=self.root, cmd=["python", "-m", "build"]))
        else:
            self._artifacts = AttrDict()
        proj = self.root.pyproject.get("project", None)
        if proj is None:
            # will be empty for old setup.py projects.
            self._contents = AttrDict()
        else:
            self._contents = AttrDict(PythonPackage(
                proj=self.root, artifacts=set(), package_name=proj["name"]))
