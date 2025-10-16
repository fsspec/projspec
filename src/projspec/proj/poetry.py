from copy import deepcopy
import toml

from projspec.proj.python_code import PythonLibrary
from projspec.utils import PickleableTomlDecoder, deep_get, deep_set


class Poetry(PythonLibrary):
    """Python packaging and dependency management

    Poetry is a tool for dependency management and packaging in Python. It allows
    you to declare the libraries your project depends on, and it will manage
    (install/update) them for you. Poetry offers a lockfile to ensure repeatable
    installs, and can build your project for distribution.
    """

    spec_doc = "https://python-poetry.org/docs/pyproject/"

    def match(self) -> bool:
        back = (
            self.proj.pyproject.get("build_system", {})
            .get("build-backend", "")
            .startswith("poetry.")
        )
        return "poetry" in self.proj.pyproject.get("tool", ()) or back

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.artifact.python_env import LockFile
        from projspec.content.environment import Environment, Precision, Stack

        # Basic details same as a python library, but older config can be in
        # tools.poetry.*
        orig = deepcopy(self.proj.pyproject)
        try:
            # would be better to factor out the code in the superclass!
            alt = self.proj.pyproject
            dep = deep_get(alt, "tool.poetry.dependencies")
            if dep:
                deep_set(alt, "project.dependencies", _table_to_list(dep))
            for k, v in deep_get(alt, "tool.poetry.group", {}).items():
                if "dependencies" in v:
                    deep_set(
                        alt, ["dependency-groups", k], _table_to_list(v["dependencies"])
                    )

            super().parse()
        finally:
            self.proj.pyproject.clear()
            self.proj.pyproject.update(orig)
        cmds = {}
        for cmd in self._contents.get("command", []):
            cmds[cmd] = Process(proj=self.proj, cmd=["poetry", "run", cmd])
        if cmds:
            self._artifacts["process"] = cmds

        self._artifacts["lock_file"] = LockFile(
            proj=self.proj,
            cmd=["poetry", "lock"],
            fn=f"{self.proj.url}/poetry.lock",
        )
        try:
            with self.proj.fs.open(f"{self.proj.url}/poetry.lock", mode="rt") as f:
                pckg = toml.load(f, decoder=PickleableTomlDecoder())
            packages = [
                f"{_['name']} =={_['version']}" for _ in pckg.get("package", [])
            ]
            packages.append(f"python {pckg['metadata']['python-versions']}")
            self.contents["environment"]["default.lock"] = Environment(
                proj=self.proj,
                packages=packages,
                stack=Stack.PIP,
                precision=Precision.LOCK,
                artifacts={self._artifacts["lock_file"]},
            )
        except (OSError, UnicodeDecodeError):
            pass
        self.artifacts["wheel"].cmd = ["poetry", "build"]


def _table_to_list(t: dict) -> list:
    return [f"{k} {v}" for k, v in t.items()]
