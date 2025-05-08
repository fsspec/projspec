import subprocess

from projspec.artifact import BaseArtifact


class Process(BaseArtifact):

    def __init__(self, cmd, *args, **kw):
        self.cmd = cmd
        self.args = args
        self.kw = kw


class SyncProcess(Process):

    def run(self):
        return subprocess.run(self.cmd + list(self.args), **self.kw)


class BackgroundProcess(Process):
    def run(self):
        return subprocess.Popen(self.cmd + list(self.args), **self.kw)
