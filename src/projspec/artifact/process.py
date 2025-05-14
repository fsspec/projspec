import subprocess

from projspec.artifact import BaseArtifact


class Process(BaseArtifact):

    def __init__(self, *args, **kw):
        super().__init__([], **kw)
        self.args: list[str] = list(args)

    def make(self):
        if self.proc is None:
            self.proc = subprocess.Popen(self.args)

    def clean(self, ):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
