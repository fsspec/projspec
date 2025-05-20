from typing import Literal

class BaseArtifact:

    def __init__(self, requires: list | None = None, **kw):
        self.requires = requires or []
        self.kw = kw
        self.proc = None

    def _is_clean(self) -> bool:
        return self.proc is None  # in general more complex

    def _is_done(self) -> bool:
        return self.proc is not None  # in general more complex

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
        raise NotImplementedError

    def remake(self):
        """Recreate artifact and any runtime it depends on"""
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
