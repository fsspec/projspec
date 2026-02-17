from projspec.proj.base import Project, ProjectExtra
from projspec.artifact import BaseArtifact

# ruff, isort, mypy ...


class PreCommit(BaseArtifact):
    """Typically used as a git hook, this lists a set of linters that a project uses."""

    def __init__(self, proj: Project, cmd=None):
        # ignore cmd: this should always be the same
        super().__init__(proj, cmd=["pre-commit", "run", "-a"])


class PreCommitted(ProjectExtra):
    """A project with pre-commit conf."""

    def match(self):
        return ".pre-commit-config.yaml" in self.proj.basenames

    def parse(self):
        self._artifacts["precommit"] = PreCommit(self.proj)
