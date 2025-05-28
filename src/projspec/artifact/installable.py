from projspec.artifact import BaseArtifact


class Wheel(BaseArtifact):
    """An installable python wheel file

    Note that in general there may be a set of wheels for different platforms.
    The actual name of the wheel file depends on platform, vcs config
    and maybe other factors. We just check if the dist/ directory is
    populated.
    """

    def _is_done(self) -> bool:
        return True

    def _is_clean(self) -> bool:
        files = self.proj.fs.glob(f"{self.proj.url}/dist/*.whl")
        return len(files) == 0

    def clean(self):
        files = self.proj.fs.glob(f"{self.proj.url}/dist/*.whl")
        self.proj.fs.rm(files)
