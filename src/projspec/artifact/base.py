

class BaseArtifact:

    def __init__(self, requires: list | None = None, **kw):
        self.requires = requires or []
        self.kw = kw
        self.proc = None

    def isclean(self):
        return self.proc is None  # in general more complex

    def make(self, *args, **kwargs):
        """Create artifact and any runtime it depends on"""
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
        return f"{type(self).__name__}, {'clean' if self.isclean() else 'ready'}"
