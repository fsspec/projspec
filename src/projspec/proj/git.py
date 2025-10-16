from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class GitRepo(ProjectSpec):
    """A version controlled repository utilising git

    git is a very common version control system for code projects.
    """

    spec_doc = "https://git-scm.com/docs/git-config#_configuration_file"

    def match(self) -> bool:
        return ".git" in self.proj.basenames

    def parse(self) -> None:
        # Actually, it's faster to read the /.git/config file, which also gives
        # the remote URLs and such.
        cont = AttrDict()
        cont["remotes"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.proj.fs.ls(f"{self.proj.url}/.git/refs/remotes", detail=False)
        ]
        cont["tags"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.proj.fs.ls(f"{self.proj.url}/.git/refs/tags", detail=False)
        ]
        cont["branches"] = [
            _.rsplit("/", 1)[-1]
            for _ in self.proj.fs.ls(f"{self.proj.url}/.git/refs/heads", detail=False)
        ]
        self._contents = cont
