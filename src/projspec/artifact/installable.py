from enum import auto
import logging
import os.path
import subprocess
from platform import architecture

from projspec.artifact import FileArtifact
from projspec.utils import Enum

logger = logging.getLogger("projspec")


class Wheel(FileArtifact):
    """An installable python wheel file

    Note that in general there may be a set of wheels for different platforms.
    The actual name of the wheel file depends on platform, vcs config
    and maybe other factors. We just check if the dist/ directory is
    populated.

    This output is intended to be _local_ - pushing to a remote location (e.g., pypi)
    is call publishing.
    """

    def __init__(self, proj, fn=None, **kw):
        super().__init__(proj=proj, fn=fn or f"{proj.url}/dist/*.whl", **kw)

    def _is_clean(self) -> bool:
        files = self.proj.fs.glob(self.fn)
        return len(files) == 0

    def clean(self):
        files = self.proj.fs.glob(self.fn)
        self.proj.fs.rm(files)


class CondaPackage(FileArtifact):
    """An installable python wheel file

    Note that in general, there may be a set of wheels for different platforms.
    The actual name of the wheel file depends on the platform, vcs config
    and maybe other factors. We just check if the dist/ directory is
    populated.

    This output is intended to be _local_ - pushing to a remote location (e.g., pypi)
    is call publishing.
    """

    def __init__(self, fn=None, name=None, **kwargs):
        super().__init__(fn=fn, **kwargs)
        self.name = name

    def _make(self, *args, **kwargs):
        import re

        logger.debug(" ".join(self.cmd))
        out = subprocess.check_output(self.cmd).decode("utf-8")
        if fn := re.match(r"'(.*?\.conda)'\n", out):
            if os.path.exists(fn.group(1)):
                self.fn = fn.group(1)

    def _is_done(self) -> bool:
        return True

    def _is_clean(self) -> bool:
        return self.fn is None or not self.proj.fs.glob(self.fn)

    def clean(self):
        if self.fn is not None:
            self.proj.fs.rm(self.fn)
            self.fn = None


class Architecture(Enum):
    """What kind of system this runs on"""

    ANDROID = "android"
    IOS = "iOS"
    LINUX = "linux"
    MACOS = "macOS"
    WEB = "web"
    WINDOWS = "windows"


types = {
    "aap": Architecture.ANDROID,
    "apk": Architecture.ANDROID,
    "deb": Architecture.LINUX,
    "dmg": Architecture.MACOS,
    "flatpak": Architecture.LINUX,
    "ipa": Architecture.IOS,
    "app.zip": Architecture.MACOS,
    "msi": Architecture.WINDOWS,
    "pkg": Architecture.MACOS,
    "pkg.tar.zst": Architecture.LINUX,
    "rpm": Architecture.LINUX,
    "web.zip": Architecture.WEB,
}


class SystemInstallablePackage(FileArtifact):
    """An Installable system package"""

    def __init__(self, proj, ext: str, fn=None, arch=None, **kw):
        self.arch = arch or types[ext]
        self.filetype = ext
        super().__init__(proj=proj, fn=fn or f"{proj.url}/dist/*.{ext}", **kw)
