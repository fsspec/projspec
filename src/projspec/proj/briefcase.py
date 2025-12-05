import platform
import sys

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


def supported(apps, app, *config):
    """Check if an app is supported on a given platform.

    Looks in the metadata for app for a `supported` key in each
    level named in config. If there isn't a table for the named config,
    or the table contains a `supported = false` declaration, the

    For example, `supported(apps, "foo", "linux", "system")` will check for:

    * A "linux" table; if there isn't, return False
    * A `supported` key in the "linux" table (defaulting True)
    * A "linux.system" table; if there isn't return False
    * A `supported` key in the "linux.system" table (defaulting True)

    If any of those results return False, the app isn't supported.
    """
    platform = apps[app].get(config[0], {"supported": False})
    supported = platform.get("supported", True)
    for part in config[1:]:
        try:
            platform = platform.get(part, {"supported": False})
            supported &= platform.get("supported", True)
        except KeyError:
            # Platform config doesn't exist
            supported = False

    return supported


class Briefcase(ProjectSpec):
    spec_doc = "https://briefcase.readthedocs.io/en/stable/reference/configuration.html"

    def match(self) -> bool:
        return "briefcase" in self.proj.pyproject.get("tool", {})

    def parse(self) -> None:
        from projspec.artifact.installable import (
            AABArtifact,
            APKArtifact,
            DEBArtifact,
            DMGArtifact,
            IPAArtifact,
            LinuxPKGArtifact,
            MSIArtifact,
            PKGArtifact,
            RPMArtifact,
            ZipArtifact,
        )

        briefcase_meta = self.proj.pyproject["tool"]["briefcase"]

        cont = AttrDict()
        self._contents = cont

        self._artifacts = AttrDict()

        apps = briefcase_meta.get("app", {})

        if sys.platform == "darwin":
            for fmt, Artifact, arg in [
                ("macOS-app", ZipArtifact, "zip"),
                ("macOS-dmg", DMGArtifact, "dmg"),
                ("macOS-pkg", PKGArtifact, "pkg"),
            ]:
                for app in apps:
                    if supported(apps, app, "macOS"):
                        self._artifacts[fmt] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", arg],
                        )

            # iOS doesn't produce an artifact directly, but it's included for
            # completeness.
            for app in apps:
                if supported(apps, app, "iOS"):
                    self._artifacts["iOS"] = IPAArtifact(
                        proj=self.proj,
                        cmd=["briefcase", "package", "iOS", "-a", app, "-p", "ipa"],
                    )

        elif sys.platform == "linux":
            # This only covers natively built packages; these can all be built
            # via Docker as well.
            release = platform.freedesktop_os_release()
            release_id = release["ID"]
            release_like = release.get("ID_LIKE", "")

            for app in apps:
                if release_id == "fedora" or "fedora" in release_like:
                    if supported(apps, app, "linux", "system", "rhel"):
                        self._artifacts["linux-rpm"] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", "rpm"],
                        )
                elif "suse" in release_like:
                    if supported(apps, app, "linux", "system", "suse"):
                        self._artifacts["linux-rpm"] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", "rpm"],
                        )
                elif release_id == "debian" or "debian" in release_like:
                    if supported(apps, app, "linux", "system", "debian"):
                        self._artifacts["linux-deb"] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", "deb"],
                        )
                elif release_id == "arch" or "arch" in release_like:
                    if supported(apps, app, "linux", "system", "arch"):
                        self._artifacts["linux-pkg"] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", "pkg"],
                        )

                if supported(apps, app, "linux", "flatpak"):
                    self._artifacts["linux-flatpak"] = IPAArtifact(
                        proj=self.proj,
                        cmd=[
                            "briefcase",
                            "package",
                            "linux",
                            "flatpak",
                            "-a",
                            app,
                            "-p",
                            "flatpak",
                        ],
                    )

        elif sys.platform == "windows":
            for fmt, Artifact, arg in [
                ("windows-app", ZipArtifact, "zip"),
                ("windows-msi", MSIArtifact, "msi"),
            ]:
                for app in apps:
                    if supported(apps, app, "windows"):
                        self._artifacts[fmt] = Artifact(
                            proj=self.proj,
                            cmd=["briefcase", "package", "-a", app, "-p", arg],
                        )

        # Android apps can be built on every platform
        for app in apps:
            if supported(apps, app, "android"):
                for fmt, Artifact, arg in [
                    ("android-aab", AABArtifact, "aab"),
                    ("android-apk", APKArtifact, "apk"),
                ]:
                    self._artifacts[fmt] = Artifact(
                        proj=self.proj,
                        cmd=[
                            "briefcase",
                            "package",
                            "android",
                            "-a",
                            app,
                            "-p",
                            arg,
                        ],
                    )

        # Web apps can be built on every platform
        for app in apps:
            if supported(apps, app, "web"):
                self._artifacts["web-zip"] = Artifact(
                    proj=self.proj,
                    cmd=[
                        "briefcase",
                        "package",
                        "web",
                        "-a",
                        app,
                        "-p",
                        "zip",
                    ],
                )
