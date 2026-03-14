import logging
from typing import Literal

import fsspec.implementations.local

from projspec.config import get_conf
from projspec.proj import Project
from projspec.utils import camel_to_snake, is_installed, run_subprocess

logger = logging.getLogger("projspec")
registry = {}


class BaseArtifact:
    """A thing that a project can o or make

    Artifacts are the "actions" of a project spec. Most typically, they involve
    calling the external tool associated with the project type in a subprocess.
    """

    def __init__(self, proj: Project, cmd: list[str] | None = None, **kwargs):
        self.proj = proj
        self.cmd = cmd
        self.proc = None
        self.__dict__.update(kwargs)

    def _is_clean(self) -> bool:
        return self.proc is None  # in general, more complex

    def _is_done(self) -> bool:
        return self.proc is not None  # in general, more complex

    def _check_runner(self):
        return self.cmd[0] in is_installed

    @property
    def state(self) -> Literal["clean", "done", "pending", ""]:
        if get_conf("remote_artifact_status") or self.proj.is_local():
            if self._is_clean():
                return "clean"
            elif self._is_done():
                return "done"
            else:
                return "pending"
        else:
            return ""

    def make(self, *args, **kwargs):
        """Create the artifact and any runtime it depends on"""
        if not self.proj.is_local():
            # Later, will implement download-and-make, although some tools
            # can already do this themselves.
            raise RuntimeError("Can't run local command on remote project")
        # this default implementation does not store any state
        self._make(*args, **kwargs)

    def _make(self, *args, **kwargs):
        logger.info("running %s", self.cmd)
        run_subprocess(self.cmd, cwd=self.proj.url, output=False, **kwargs)

    def remake(self):
        """Recreate the artifact and any runtime it depends on"""
        self.clean()
        self.make()

    def clean(self):
        """Remove artifact"""
        # this default implementation leaves nothing to clean
        pass

    def __repr__(self):
        return f"{type(self).__name__}, '{' '.join(self.cmd)}', {self.state}"

    def _repr2(self):
        return f"{' '.join(self.cmd)}, {self.state}"

    @classmethod
    def __init_subclass__(cls, **kwargs):
        sn = cls.snake_name()
        registry[sn] = cls

    @classmethod
    def snake_name(cls):
        return camel_to_snake(cls.__name__)

    def to_dict(self, compact=True):
        """Distil the instance to JSON compatible dict

        compact: if True, will produce condensed output, perhaps justa  string.
        """
        if compact:
            return self._repr2()
        dic = {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in ("proj", "proc")
        }
        dic["klass"] = ["artifact", self.snake_name()]
        dic["proc"] = None
        return dic


def get_cls(name: str) -> type[BaseArtifact]:
    """Find an artifact class by snake-case name."""
    return registry[name]


class FileArtifact(BaseArtifact):
    """Specialised artifacts, where the output is one or more files

    Ideally, we can know beforehand the path expected for the output.
    """

    # TODO: account for outputs to a directory/glob pattern, so we can
    #   apply to wheel; or unknown output location, e.g., conda-build.

    def __init__(self, proj: Project, fn: str, **kw):
        self.fn = fn
        super().__init__(proj, **kw)

    def _is_done(self) -> bool:
        return self.proj.fs.glob(self.fn)

    def _is_clean(self) -> bool:
        return not self.proj.fs.glob(self.fn)
