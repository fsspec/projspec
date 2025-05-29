from typing import Type
from functools import cached_property


import fsspec

from projspec.utils import AttrDict
from projspec.proj.base import ProjectSpec


class PythonCode(ProjectSpec):
    """Code directly importable by python

    This applies to directories with __init__.py (i.e., not isolated .py files,
    or eggs). Could include .zip in theory.

    Such a structure does not declare any envs, deps, etc. It contains
    nothing interesting _except_ code.

     A package is executable if it contains a ``__main__.py`` file.
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
        basenames = set(_.rsplit("/", 1)[-1] for _ in self.root.filelist)

        if "build-system" in self.root.pyproject:
            # should imply that "python -m build" can run
            # With --wheel ?
            self._artifacts = AttrDict(Wheel(proj=self.root, cmd=["python", "-m", "build"]))
        elif "setup.py" in basenames:
            self._artifacts = AttrDict(Wheel(proj=self.root, cmd=["python", "setup.py", "bdist_wheel"]))
        else:
            self._artifacts = AttrDict()
        # not attempting to parse setup.py, although most commonly a subdirectory with
        # the same name as the repo is the python package
        proj = self.root.pyproject.get("project", None)
        if proj is None:
            # will be empty for old setup.py projects.
            self._contents = AttrDict()
        else:
            self._contents = AttrDict(PythonPackage(
                proj=self.root, artifacts=set(), package_name=proj["name"]))
