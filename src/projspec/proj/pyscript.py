import toml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


class PyScript(ProjectSpec):
    spec_doc = "https://docs.pyscript.net/2023.11.2/user-guide/configuration/"

    def match(self) -> bool:
        # actually, config can be specified by a local path in the repo, but this is rare;
        # also you can just declare things to install as you go, which we won't be able to
        # guess.
        return not {"pyscript.toml", "pyscript.json"}.isdisjoint(
            self.root.basenames
        )

    def parse(self) -> None:
        try:
            with self.root.fs.open(f"{self.root.url}/pyscript.toml", "rt") as f:
                meta = toml.load(f)
        except FileNotFoundError:
            with self.root.fs.open(f"{self.root.url}/pyscript.json", "rt") as f:
                meta = toml.load(f)
        cont = AttrDict()
        if "packages" in meta:
            cont["environment"] = AttrDict(default=meta["packages"])
        self._contents = cont

        # perhaps a local deployment can be a reasonable artifact
        # https://github.com/pyscript/pyscript-cli
        self._artifacts = AttrDict()
