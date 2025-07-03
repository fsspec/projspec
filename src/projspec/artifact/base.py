import logging
import subprocess
from typing import Literal

import fsspec.implementations.local

from projspec.proj import Project
from projspec.utils import is_installed

logger = logging.getLogger("projspec")


class BaseArtifact:
    def __init__(
        self,
        proj: Project,
        requires: list | None = None,
        cmd: list[str] | None = None,
        **kw,
    ):
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
        if not isinstance(
            self.proj.fs, fsspec.implementations.local.LocalFileSystem
        ):
            # Later, will implement download-and-make, although some tools
            # can already do this themselves.
            raise RuntimeError("Can't run local command on remote project")
        logger.debug(" ".join(self.cmd))
        # this default implementation does not store any state
        self._make(*args, **kwargs)

    def _make(self, *args, **kwargs):
        subprocess.check_call(self.cmd, cwd=self.proj.url, **self.kw)

    def remake(self, reqs=False):
        """Recreate artifact and any runtime it depends on"""
        if reqs:
            self.clean_req()
        self.clean()
        self.make()

    def clean_req(self):
        for req in self.requires:
            req.clean()

    def clean(self):
        """Remove artifact"""
        # this default implementation leaves nothing to clean
        pass

    def __repr__(self):
        return f"{type(self).__name__}, {self.state}"
