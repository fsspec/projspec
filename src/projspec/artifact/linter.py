from projspec import Project
from projspec.artifact import BaseArtifact

# ruff, isort, mypy ...


class PreCommit(BaseArtifact):
    """Typically used as a git hook, this lists a set of linters that a project uses."""

    # recognised by the presence o .pre-commit-config.yaml, but we don't need
    # to parse it in order to run.

    def __init__(self, proj: Project, cmd=None):
        # ignore cmd: this should always be the same
        super().__init__(proj, cmd=["pre-commit", "run", "-a"])
