import toml

from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict

# UV also allows dependencies (and other metadata)
# to be declared inside scripts, which means you can have one-file projects.
# https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies
# example:
# /// script
# # dependencies = [
# #   "requests<3",
# #   "rich",
# # ]
# # ///


class UVScript(ProjectSpec):
    """Single-file project runnable by UV as a script

    Metadata are declared inline in the script header
    See https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies

    Note that UV explicitly allows running these directly from HTTP URLs.
    """

    def match(self):
        return self.root.url.endswith(("py", "pyw"))

    def parse(self):
        with self.root.fs.open(self.root.url) as f:
            txt = f.read().decode()
        lines = txt.split("# /// script\n", 1)[1].txt.split("# ///\n", 1)[0]
        meta = "\n".join(line[2:] for line in lines.split("\n"))
        toml.loads(meta)
        # once we have the meta, we can reuse UVProject
        #
        # Apparently, uv.lock may or may not be in the same directory


class UVProject(ProjectSpec):
    """UV-runnable project

    Note: uv can run any python project, but this tests for uv-specific
    config. See also ``projspec.deploty.python.UVRunner``.
    """

    def match(self):
        contents = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in contents}
        if (
            "uv.lock" in basenames
            or "uv.toml" in basenames
            or ".python-version" in basenames
        ):
            return True
        if "uv" in self.root.pyproject.get("tools", {}):
            return True
        if (
            self.root.pyproject.get("build-system", {}).get("build-backend", "")
            == "uv_build"
        ):
            return True
        if ".venv" in basenames:
            try:
                with self.root.fs.open(
                    f"{self.root.url}/.venv/pyvenv.cfg", "rt"
                ) as f:
                    txt = f.read()
                return b"uv =" in txt
            except (OSError, FileNotFoundError):
                pass
        return False

    def parse(self):
        conf = self.root.pyproject.get("tools", {}).get("uv", {})
        try:
            with self.root.fs.open(f"{self.root.url}/uv.toml", "rt") as f:
                conf2 = toml.load(f)
        except (OSError, FileNotFoundError):
            conf2 = {}
        conf.update(conf2)
        try:
            with self.root.fs.open(f"{self.root.url}/uv.lock", "rt") as f:
                lock = toml.load(f)
        except (OSError, FileNotFoundError):
            lock = {}

        # TODO: fill out the following
        lock.clear()

        # environment spec
        # commands
        # python package (unless tools.uv.package == False)
        self._contents = AttrDict()

        # lockfile
        # runtime environment
        # process from defined commands
        self._artifacts = AttrDict()
