from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


def supported(apps: dict, app: str, *config) -> bool:
    """Check if an app is supported on a given platform.

    Looks in the metadata for app for a `supported` key in each
    level named in config. If there isn't a table for the named config,
    or the table contains a `supported = false` declaration, skip it.

    For example, `supported(apps, "foo", "linux", "system")` will check for:

    * A "linux" table; if there isn't, return False
    * A `supported` key in the "linux" table (defaulting True)
    * A "linux.system" table; if there isn't return False
    * A `supported` key in the "linux.system" table (defaulting True)

    If any of those results return False, the app isn't supported.
    """
    plat = apps[app].get(config[0], {"supported": False})
    supp = plat.get("supported", True)
    for part in config[1:]:
        try:
            plat = plat.get(part, {"supported": False})
            supp &= plat.get("supported", True)
        except KeyError:
            # Platform config doesn't exist
            supp = False

    return supp


class Briefcase(ProjectSpec):
    spec_doc = "https://briefcase.readthedocs.io/en/stable/reference/configuration.html"

    def match(self) -> bool:
        return "briefcase" in self.proj.pyproject.get("tool", {})

    def parse(self) -> None:
        from projspec.artifact.installable import (
            Architecture,
            SystemInstallablePackage,
        )

        briefcase_meta = self.proj.pyproject["tool"]["briefcase"]

        cont = AttrDict()
        self._contents = cont
        self._artifacts = AttrDict()

        apps = briefcase_meta.get("app", {})

        # TODO: app name is not encoded in the artifact, so multiple outputs
        #  will overwrite.
        for app in apps:
            for filetype in ("zip", "dmg", "pkg"):
                if supported(apps, app, "macOS"):
                    self._artifacts[filetype] = SystemInstallablePackage(
                        proj=self.proj,
                        ext=filetype,
                        arch=Architecture.MACOS,
                        cmd=["briefcase", "package", "-a", app, "-p", filetype],
                    )

            # iOS doesn't produce an artifact directly, but it's included for
            # completeness.
            if supported(apps, app, "iOS"):
                self._artifacts["iOS"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="ipa",
                    arch=Architecture.IOS,
                    cmd=["briefcase", "package", "iOS", "-a", app, "-p", "ipa"],
                )

            if supported(apps, app, "linux", "system", "rhel"):
                self._artifacts["linux-rpm"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="rpm",
                    arch=Architecture.LINUX,
                    cmd=["briefcase", "package", "-a", app, "-p", "rpm"],
                )
            if supported(apps, app, "linux", "system", "suse"):
                self._artifacts["linux-rpm"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="rpm",
                    arch=Architecture.LINUX,
                    cmd=["briefcase", "package", "-a", app, "-p", "rpm"],
                )
            if supported(apps, app, "linux", "system", "debian"):
                self._artifacts["linux-deb"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="deb",
                    arch=Architecture.LINUX,
                    cmd=["briefcase", "package", "-a", app, "-p", "deb"],
                )
            if supported(apps, app, "linux", "system", "arch"):
                self._artifacts["linux-pkg"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="pkg.tar.zstd",
                    arch=Architecture.LINUX,
                    cmd=["briefcase", "package", "-a", app, "-p", "pkg"],
                )

            if supported(apps, app, "linux", "flatpak"):
                self._artifacts["linux-flatpak"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="flatpack",
                    arch=Architecture.LINUX,
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

            if supported(apps, app, "windows"):
                self._artifacts["windows-msi"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="msi",
                    arch=Architecture.WINDOWS,
                    cmd=["briefcase", "package", "-a", app, "-p", "msi"],
                )

            if supported(apps, app, "android"):
                for fmt, Artifact, arg in [
                    ("android-aab", SystemInstallablePackage, "aab"),
                    ("android-apk", SystemInstallablePackage, "apk"),
                ]:
                    self._artifacts[fmt] = Artifact(
                        proj=self.proj,
                        ext=fmt,
                        arch=Architecture.ANDROID,
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

            if supported(apps, app, "web"):
                self._artifacts["web-zip"] = SystemInstallablePackage(
                    proj=self.proj,
                    ext="web.zip",
                    arch=Architecture.WEB,
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
