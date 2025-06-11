import toml

from projspec.proj import ProjectSpec

# pixi supports extensions, e.g., ``pixi global install``
# which is how you get access to pixi-pack, for instance.


class Pixi(ProjectSpec):
    def match(self) -> bool:
        meta = self.root.pyproject.get("tools", {}).get("pixi", {})
        basenames = (_.rsplit("/", 1)[-1] for _ in self.root.filelist)
        return bool(meta) or "pixi.toml" in basenames

    def parse(self) -> None:
        meta = self.root.pyproject.get("tools", {}).get("pixi", {})
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in self.root.filelist}
        if "pixi.toml" in basenames:
            try:
                with self.root.fs.open(basenames["pixi.toml"], "rb") as f:
                    meta.update(toml.load(f.read().decode()))
            except (OSError, ValueError, UnicodeDecodeError):
                pass
        if not meta:
            raise ValueError
