import logging
import subprocess
from typing import Literal

from projspec.proj import Project
from projspec.utils import is_installed

logger = logging.getLogger("projspec")


class BaseArtifact:

    def __init__(self, proj: Project, requires: list | None = None, cmd: list[str]|None=None, **kw):
        self.proj = proj
        self.requires = requires or []
        self.cmd = cmd
        self.kw = kw
        self.proc = None

    def _is_clean(self) -> bool:
        return self.proc is None  # in general more complex

    def _is_done(self) -> bool:
        return self.proc is not None  # in general more complex

    def _check_runner(self):
        return self.cmd[0] in is_installed

    @property
    def state(self) -> Literal["clean", "done", "pending"]:
        if self._is_clean():
            return "clean"
        elif self._is_done():
            return "done"
        else:
            return "pending"

    def make(self, *args, **kwargs):
        """Create the artifact and any runtime it depends on"""
        # this implementation covers many uses, but maybe
        # we should provide different ones for "call", "background" etc
        logger.debug(" ".join(self.cmd))
        # TODO: set CWD if fs is local
        # TODO: prepend to env["PATH"] if using specific (python) runtime
        subprocess.check_call(self.cmd, **self.kw)

    def remake(self, reqs=False):
        """Recreate artifact and any runtime it depends on"""
        if reqs:
            for req in self.requires:
                req.remake(reqs=reqs)
        self.clean()
        self.make()

    def clean_req(self):
        for req in self.requires:
            req.clean()

    def clean(self):
        """Remove artifact"""
        raise NotImplementedError

    def __repr__(self):
        return f"{type(self).__name__}, {self.state}"
