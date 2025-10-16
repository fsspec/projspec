import subprocess

from projspec.artifact import BaseArtifact


class Process(BaseArtifact):
    """A simple process where we know nothing about what it does, only if it's running.

    Can include batch jobs and long-running services.
    """

    def _make(self):
        if self.proc is None:
            self.proc = subprocess.Popen(self.cmd, **self.kw)

    def _is_done(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def clean(
        self,
    ):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
