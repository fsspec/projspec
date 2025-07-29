from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class GitRepo(ProjectSpec):
    def match(self) -> bool:
        return ".git" in self.root.basenames

    def parse(self) -> None:
        cont = AttrDict()
        cont["remotes"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.root.fs.ls(
                f"{self.root.url}/.git/refs/remotes", detail=False
            )
        ]
        cont["tags"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.root.fs.ls(
                f"{self.root.url}/.git/refs/tags", detail=False
            )
        ]
        cont["branches"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.root.fs.ls(
                f"{self.root.url}/.git/refs/heads", detail=False
            )
        ]
        self._contents = cont
