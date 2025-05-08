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
    # note: python can actually import any directory, but let's ignore cases without
    # python code

    @staticmethod
    def match(path: str, storge_options: dict | None = None) -> bool:
        if path.endswith(".py"):
            return True
        fs, url = fsspec.url_to_fs(path)
        try:
            contents = fs.ls(url)
        except FileNotFoundError:
            return False
        basenames = set(_.rsplit("/", 1)[-1] for _ in contents)
        return "__init__.py" in basenames

    @cached_property
    def contents(self):
        from projspec.content.package import PythonPackage
        return AttrDict(PythonPackage(package_name=self.url.rsplit("/", 1)[-1]))

    @cached_property
    def artifacts(self):
        from projspec.content.executable import Command
        from projspec.runner.python import SystemPython
        arg = []
        if not self.url.endswith(".py"):
            filelist = self.fs.ls(self.url)
            exe = [_ for _ in filelist if _.rsplit("/", 1)[-1] == "__main__.py"]
            if exe:
                arg.append(AttrDict(command=AttrDict(main=Command(SystemPython(), exe[0]))))
        return AttrDict(*arg)
