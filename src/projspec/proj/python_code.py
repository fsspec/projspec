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

    @cached_property
    def contents(self):
        from projspec.content.package import PythonPackage
        from projspec.content.executable import Command

        out = AttrDict(PythonPackage(artifact=None, package_name=self.path.rsplit("/", 1)[-1]))
        arts = self.artifacts
        if arts:
            art = arts["process"]["main"]
            out["command"] = AttrDict(main=Command(artifact=art, args=art.args))
        return out

    @cached_property
    def artifacts(self):
        from projspec.artifact.process import Process
        out = AttrDict()
        exe = [_ for _ in self.root.filelist if _.rsplit("/", 1)[-1] == "__main__.py"]
        if exe:
            out["process"] = AttrDict(main=Process("python", exe[0]))

        return out


class PythonLbrary(ProjectSpec):
    """Complete python buildable project

    Defined by existence of pyproject.toml or setup.py.
    """
    def match(self) -> bool:
        basenames = set(_.rsplit("/", 1)[-1] for _ in self.root.filelist)
        return "pyproject.toml" in basenames or "setup.py" in basenames

    @cached_property
    def artifacts(self):
        from projspec.artifact.installable import Wheel
        proj = self.root.pyproject.get("project", None)
        if proj.get("build-system"):
            # should imply that "python -m build" can run
            return AttrDict(Wheel())
        return AttrDict()

    @cached_property
    def contents(self):
        from projspec.content.package import PythonPackage
        proj = self.root.pyproject.get("project", None)
        if proj is None:
            # will be empty for old setup.py projects.
            return AttrDict()
        return AttrDict(PythonPackage(artifact=None, package_name=proj["name"]))
