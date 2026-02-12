import toml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict, PickleableTomlDecoder, make_and_copy


class PyScript(ProjectSpec):
    """PyScript is an open source platform for Python in the browser.

    This spec is the canonical way to provide configuration, and included in new template
    apps on pyscript.com.
    """

    spec_doc = "https://docs.pyscript.net/2023.11.2/user-guide/configuration/"

    def match(self) -> bool:
        # actually, config can be specified by a local path in the repo, but this is rare;
        # also you can just declare things to install as you go, which we won't be able to
        # guess.
        return not {"pyscript.toml", "pyscript.json"}.isdisjoint(self.proj.basenames)

    def parse(self) -> None:
        from projspec.content.environment import Environment, Precision, Stack
        from projspec.artifact.process import Server

        try:
            with self.proj.fs.open(f"{self.proj.url}/pyscript.toml", "rt") as f:
                meta = toml.load(f, decoder=PickleableTomlDecoder())
        except FileNotFoundError:
            with self.proj.fs.open(f"{self.proj.url}/pyscript.json", "rt") as f:
                meta = toml.load(f, decoder=PickleableTomlDecoder())
        cont = AttrDict()
        if "packages" in meta:
            cont["environment"] = AttrDict(
                default=Environment(
                    proj=self.proj,
                    artifacts=set(),
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                    packages=meta["packages"],
                )
            )
        self._contents = cont

        # perhaps a local deployment can be a reasonable artifact
        # https://github.com/pyscript/pyscript-cli
        self._artifacts = AttrDict(
            {"server": Server(proj=self.proj, cmd=["pyscript", "run"])}
        )

    @staticmethod
    def _create(path: str) -> None:
        import subprocess

        with make_and_copy(path) as tmp:
            cmd = [
                "pyscript",
                "create",
                "--app-description",
                "projspec-app",
                "--author-name",
                "temp",
                "--author-email",
                "temp",
                tmp,
            ]
            subprocess.check_call(cmd)
