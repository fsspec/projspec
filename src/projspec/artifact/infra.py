"""Infrastructure and deployment artifact types."""

from projspec.artifact.base import BaseArtifact, FileArtifact
from projspec.proj.base import Project
from projspec.utils import run_subprocess


class ComposeStack(BaseArtifact):
    """A multi-service stack managed by Docker Compose.

    ``make()``  runs ``docker compose up -d``
    ``clean()`` runs ``docker compose down``
    ``state``   is inferred by ``docker compose ps`` (checks for running services).
    """

    icon = "layer-group"

    def __init__(self, proj: Project, file: str = "docker-compose.yml", **kwargs):
        self.compose_file = file
        cmd = ["docker", "compose", "-f", file, "up", "-d"]
        super().__init__(proj, cmd=cmd, **kwargs)

    def _make(self, **kwargs):
        run_subprocess(self.cmd, cwd=self.proj.url, output=False, **kwargs)

    def clean(self):
        run_subprocess(
            ["docker", "compose", "-f", self.compose_file, "down"],
            cwd=self.proj.url,
            output=False,
        )

    def _is_done(self) -> bool:
        try:
            result = run_subprocess(
                ["docker", "compose", "-f", self.compose_file, "ps", "-q"],
                cwd=self.proj.url,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _is_clean(self) -> bool:
        return not self._is_done()


class StaticSite(FileArtifact):
    """A static website produced by a build tool (MkDocs, Sphinx, Docusaurus, Quarto, etc.).

    ``fn`` should be the glob pattern for the output index file, e.g.
    ``<proj>/site/index.html``.
    """

    icon = "globe"

    pass


class TerraformPlan(FileArtifact):
    """A saved Terraform execution plan file (``terraform plan -out plan.tfplan``).

    ``make()`` runs ``terraform plan -out plan.tfplan``
    ``clean()`` deletes the plan file
    """

    icon = "cloud"

    def __init__(self, proj: Project, plan_file: str = "plan.tfplan", **kwargs):
        fn = f"{proj.url}/{plan_file}"
        cmd = ["terraform", "plan", "-out", plan_file]
        super().__init__(proj, fn=fn, cmd=cmd, **kwargs)

    def clean(self):
        try:
            self.proj.fs.rm(self.fn)
        except FileNotFoundError:
            pass
