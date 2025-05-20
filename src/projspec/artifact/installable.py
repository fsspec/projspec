from projspec.artifact import BaseArtifact


class Wheel(BaseArtifact):
    """An installable python wheel file

    Note that in general there may be a set of wheels for different platforms.
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def make(self, *args, **kwargs):
        """Create the artifact and any runtime it depends on"""
        raise NotImplementedError

