import subprocess

from projspec.artifact import BaseArtifact


class Process(BaseArtifact):
    """A process where we know nothing about what it does"""

    def __init__(self, *args, **kw):
        super().__init__([], **kw)
        self.args: list[str] = list(args)

    def make(self):
        if self.proc is None:
            self.proc = subprocess.Popen(self.args, **self.kw)

    def _is_done(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def clean(self, ):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
