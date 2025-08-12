import toml

from projspec.proj.python_code import PythonLibrary
from projspec.utils import PickleableTomlDecoder


class Poetry(PythonLibrary):
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

        # Basic details same as a python library.
        # A bunch of settings in `tool.poetry` are still allowed, if deprecated.
        super().parse()
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
            with self.proj.fs.open(
                f"{self.proj.url}/poetry.lock", mode="rt"
            ) as f:
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
