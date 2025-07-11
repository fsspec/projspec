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

    spec_doc = "https://docs.astral.sh/uv/reference/settings/"

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
        from projspec.artifact.installable import Wheel
        from projspec.artifact.python_env import LockFile, VirtualEnv
        from projspec.content.environment import Environment, Precision, Stack

        meta = self.root.pyproject
        conf = meta.get("tools", {}).get("uv", {})
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

        envs = AttrDict()
        # TODO: uv allows dependencies with source=, which would show us where the
        #  sub-packages in a project are
        if "dependencies" in meta.get("project", {}):
            # conf key [tool.uv.pip] means optional-dependencies may be included here
            envs["default"] = Environment(
                proj=self.root,
                stack=Stack.PIP,
                precision=Precision.SPEC,
                packages=meta["project"]["dependencies"],
                artifacts=set(),
            )
        envs.update(
            {
                k: Environment(
                    proj=self.root,
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                    packages=v,
                    artifacts=set(),
                )
                for k, v in conf.get("project", {})
                .get("dependency-groups", {})
                .items()
            }
        )
        if "dev-dependencies" in conf:
            envs["dev"] = Environment(
                proj=self.root,
                stack=Stack.PIP,
                precision=Precision.SPEC,
                packages=conf["dev-dependencies"],
                artifacts=set(),
            )

        self._contents = AttrDict()
        if envs:
            self._contents["environment"] = envs

        # TODO: process from defined commands
        self._artifacts = AttrDict(
            lock=AttrDict(
                default=LockFile(
                    proj=self.root,
                    cmd=["uv", "lock"],
                    fn=f"{self.root.url}/uv.lock",
                )
            ),
            venv=AttrDict(
                default=VirtualEnv(
                    proj=self.root,
                    cmd=["uv", "sync"],
                    fn=f"{self.root.url}/.venv",
                )
            ),
        )
        if conf.get("package", True):
            self._artifacts["wheel"] = Wheel(
                proj=self.root,
                cmd=["uv", "build"],
            )

        if lock:
            pkg = [f"python {lock['requires-python']}"]
            # TODO: check for source= packages as opposed to pip wheel installs
            pkg.extend(
                [
                    f"{_['name']} =={_.get('version', '')}"
                    for _ in lock["package"]
                ]
            )
            envs["lockfile"] = Environment(
                proj=self.root,
                stack=Stack.PIP,
                precision=Precision.LOCK,
                packages=pkg,
                artifacts={self._artifacts["venv"]["default"]},
            )
