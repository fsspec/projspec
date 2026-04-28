from projspec.artifact import BaseArtifact
from projspec.proj.base import Project
from projspec.utils import run_subprocess


class Deployment(BaseArtifact):
    """A named release deployed to an external orchestrator (e.g. a Kubernetes cluster).

    Unlike a local :class:`~projspec.artifact.process.Process`, a ``Deployment``
    has no local subprocess handle.  "Done" is inferred by querying the
    orchestrator; "clean" means the release has been uninstalled.

    Subclasses should override :meth:`_is_done`, :meth:`_is_clean`, and
    :meth:`clean` for their specific orchestrator.  The default implementations
    here are suitable for a Helm release:

    * :meth:`make` runs ``helm upgrade --install <release> .``
    * :meth:`clean` runs ``helm uninstall <release>``
    * :meth:`_is_done` / :meth:`_is_clean` query ``helm status <release>``
    """

    icon = "☁️"

    def __init__(
        self,
        proj: Project,
        cmd: list[str] | None = None,
        release: str = "",
        clean_cmd: list[str] | None = None,
        **kwargs,
    ):
        self.release = release
        self.clean_cmd = clean_cmd
        super().__init__(proj, cmd=cmd, **kwargs)

    def _make(self, **kwargs):
        run_subprocess(self.cmd, cwd=self.proj.url, output=False, **kwargs)

    def clean(self):
        """Tear down the deployment (e.g. ``helm uninstall <release>``)."""
        if self.clean_cmd:
            run_subprocess(self.clean_cmd, cwd=self.proj.url, output=False)

    def _is_done(self) -> bool:
        """Return True when the release exists and is deployed."""
        return False  # conservative default; subclasses or callers may override

    def _is_clean(self) -> bool:
        """Return True when no release is present."""
        return True  # conservative default


class HelmDeployment(Deployment):
    """A Helm release deployed to the active Kubernetes cluster.

    :param release: the Helm release name passed to ``helm upgrade --install``.

    ``make()`` runs::

        helm upgrade --install <release> .

    ``clean()`` runs::

        helm uninstall <release>

    ``state`` is resolved by running ``helm status <release>``:

    * ``"done"``  — release exists and is deployed (exit code 0)
    * ``"clean"`` — release does not exist (exit code non-zero / not found)
    """

    icon = "☸️"

    def __init__(self, proj: Project, release: str, **kwargs):
        cmd = ["helm", "upgrade", "--install", release, "."]
        clean_cmd = ["helm", "uninstall", release]
        super().__init__(proj, cmd=cmd, release=release, clean_cmd=clean_cmd, **kwargs)

    def _is_done(self) -> bool:
        try:
            run_subprocess(
                ["helm", "status", self.release],
                cwd=self.proj.url,
                output=False,
            )
            return True
        except Exception:
            return False

    def _is_clean(self) -> bool:
        return not self._is_done()
