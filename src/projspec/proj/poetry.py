import toml

from projspec.proj.python_code import PythonLibrary


class Poetry(PythonLibrary):
    spec_doc = "https://python-poetry.org/docs/pyproject/"

    def match(self) -> bool:
        back = (
            self.root.pyproject.get("build_system", {})
            .get("build-backend", "")
            .startswith("poetry.")
        )
        return "poetry" in self.root.pyproject.get("tool", ()) or back

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.artifact.python_env import LockFile
        from projspec.content.environment import Environment, Precision, Stack

        # Basic details same as a python library.
        # A bunch of settings in `tool.poetry` are still allowed, if deprecated.
        super().parse()
        cmds = {}
        for cmd in self._contents.get("command", []):
            cmds[cmd] = Process(proj=self.root, cmd=["poetry", "run", cmd])
        if cmds:
            self._artifacts["process"] = cmds

        self._artifacts["lock"] = LockFile(
            proj=self.root,
            cmd=["poetry", "lock"],
            fn=f"{self.root.url}/poetry.lock",
        )
        try:
            with self.root.fs.open(
                f"{self.root.url}/poetry.lock", mode="rt"
            ) as f:
                pckg = toml.load(f)
            packages = [
                f"{_['name']} =={_['version']}" for _ in pckg.get("package", [])
            ]
            packages.append(f"python {pckg['metadata']['python-versions']}")
            self.contents["environment"]["default.lock"] = Environment(
                proj=self.root,
                packages=packages,
                stack=Stack.PIP,
                precision=Precision.LOCK,
                artifacts={self._artifacts["lock"]},
            )
        except (OSError, UnicodeDecodeError):
            pass
        self.artifacts["wheel"].cmd = ["poetry", "build"]
