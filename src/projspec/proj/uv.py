from hatch.utils import toml
from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class UVProject(ProjectSpec):
    """UV-runnable project

    Note: uv can run any python project, but this tests for uv-specific
    config. See also ``projspec.deploty.python.UVRunner``.
    """

    def match(self):
        contents = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in contents}
        if "uv.lock" in basenames or "uv.toml" in basenames or ".python-version" in basenames:
            return True
        if "uv" in self.root.pyproject.get("tools", {}):
            return True
        if self.root.pyproject.get("build-system", {}).get("build-backend", "") == "uv_build":
            return True
        if ".venv" in basenames:
            try:
                with self.root.fs.open(f"{self.root.url}/.venv/pyvenv.cfg", "rb") as f:
                    txt = f.read()
                return b"uv =" in txt
            except (FileNotFoundError, IOError):
                pass
        return False

    def parse(self) -> AttrDict:
        conf = self.root.pyproject.get("tools", {}).get("uv", {})
        try:
            with self.root.fs.open(f"{self.root.url}/uv.toml", "rb") as f:
                conf2 = toml.load(f)
        except (FileNotFoundError, IOError):
            conf2 = {}
        conf.update(conf2)
        try:
            with self.root.fs.open(f"{self.root.url}/uv.lock", "rb") as f:
                lock = toml.load(f)
        except (FileNotFoundError, IOError):
            lock = {}

        # environment spec
        # commands
        # python package (unless tools.uv.package == False)
        self._contents = AttrDict()

        # lockfile
        # runtime environment
        # process from defined commands
        self._artifacts = AttrDict()
