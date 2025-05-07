import subprocess
from projspec.runner import BaseRunner


class SystemPython(BaseRunner):
    """Simplest way to execute python, using executable on the PATH"""
    proc = None

    def ready(self) -> bool:
        # since there is no setup, we assume we can always at least *try* to
        # run something; it may fail on execution.
        # possible general "which": https://stackoverflow.com/a/379535/3821154
        return True

    def setup(self, **kwargs):
        # no setup to run
        pass

    def run(self, path: str, *args: tuple[str, ...], background: bool = True, **kwargs
            ) -> subprocess.CompletedProcess | subprocess.Popen:
        """

        :param path: module to run
        :param args: further command line arguments
        :param background: whether to return while the process is still active
            (it will be cleaned up only explicitly or at interpreter exit)
        :param kwargs: passed to subprocess
        :return: process object (background) or result
        """
        cmd = ["python", path, *args]
        if background:
            self.proc = subprocess.Popen(cmd, **kwargs)
            return self.proc
        else:
            return subprocess.run(cmd, **kwargs)

    def clean(self):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
