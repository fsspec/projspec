import toml

from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.utils import AttrDict, PickleableTomlDecoder


def _parse_conf(self: ProjectSpec, conf: dict):
    from projspec.artifact.installable import Wheel
    from projspec.artifact.python_env import LockFile, VirtualEnv
    from projspec.content.environment import Environment, Precision, Stack

    meta = self.proj.pyproject

    envs = AttrDict()
    # TODO: uv allows dependencies with source=, which would show us where the
    #  sub-packages in a project are
    if "dependencies" in meta.get("project", {}):
        # conf key [tool.uv.pip] means optional-dependencies may be included here
        envs["default"] = Environment(
            proj=self.proj,
            stack=Stack.PIP,
            precision=Precision.SPEC,
            packages=meta["project"]["dependencies"],
            artifacts=set(),
        )
    envs.update(
        {
            k: Environment(
                proj=self.proj,
                stack=Stack.PIP,
                precision=Precision.SPEC,
                packages=v,
                artifacts=set(),
            )
            for k, v in conf.get("project", {}).get("dependency-groups", {}).items()
        }
    )
    if "dev-dependencies" in conf:
        envs["dev"] = Environment(
            proj=self.proj,
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
        lock_file=AttrDict(
            default=LockFile(
                proj=self.proj,
                cmd=["uv", "lock"],
                fn=f"{self.proj.url}/uv.lock",
            )
        ),
        virtual_env=AttrDict(
            default=VirtualEnv(
                proj=self.proj,
                cmd=["uv", "sync"],
                fn=f"{self.proj.url}/.venv",
            )
        ),
    )
    if conf.get("package", True):
        self._artifacts["wheel"] = Wheel(
            proj=self.proj,
            cmd=["uv", "build"],
        )


class UvScript(ProjectSpec):
    """Single-file project runnable by UV as a script

    Metadata are declared inline in the script header
    See https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies

    """

    spec_doc = "https://docs.astral.sh/uv/reference/settings/"

    def match(self):
        # this is a file, not a directory
        return self.proj.url.endswith(("py", "pyw"))

    def parse(self):
        try:
            with self.proj.fs.open(self.proj.url) as f:
                txt = f.read().decode()
        except OSError as e:
            raise ParseFailed from e
        lines = txt.split("# /// script\n", 1)[1].txt.split("# ///\n", 1)[0]
        meta = "\n".join(line[2:] for line in lines.split("\n"))
        _parse_conf(self, toml.loads(meta, decoder=PickleableTomlDecoder()))
        # if URL/filesystem is local or http(s):
        # self.artifacts["process"] = Process(
        #     proj=self.root, cmd=['uvx', self.root.url]
        # )


class Uv(ProjectSpec):
    """UV-runnable project

    Note: uv can run any python project, but this tests for uv-specific
    config.
    """

    def match(self):
        if not {"uv.lock", "uv.toml", ".python-version"}.isdisjoint(
            self.proj.basenames
        ):
            return True
        if "uv" in self.proj.pyproject.get("tools", {}):
            return True
        if (
            self.proj.pyproject.get("build-system", {}).get("build-backend", "")
            == "uv_build"
        ):
            return True
        if ".venv" in self.proj.basenames:
            try:
                with self.proj.fs.open(f"{self.proj.url}/.venv/pyvenv.cfg", "rt") as f:
                    txt = f.read()
                return b"uv =" in txt
            except (OSError, FileNotFoundError):
                pass
        return False

    def parse(self):
        from projspec.content.environment import Environment, Precision, Stack

        meta = self.proj.pyproject
        conf = meta.get("tools", {}).get("uv", {})
        try:
            with self.proj.fs.open(f"{self.proj.url}/uv.toml", "rt") as f:
                conf2 = toml.load(f, decoder=PickleableTomlDecoder())
        except (OSError, FileNotFoundError):
            conf2 = {}
        conf.update(conf2)
        try:
            with self.proj.fs.open(f"{self.proj.url}/uv.lock", "rt") as f:
                lock = toml.load(f, decoder=PickleableTomlDecoder())
        except (OSError, FileNotFoundError):
            lock = {}
        _parse_conf(self, conf)

        if lock:
            pkg = [f"python {lock['requires-python']}"]
            # TODO: check for source= packages as opposed to pip wheel installs
            pkg.extend([f"{_['name']}{_vers(_)}" for _ in lock["package"]])
            self._contents.setdefault("environment", {})["lockfile"] = Environment(
                proj=self.proj,
                stack=Stack.PIP,
                precision=Precision.LOCK,
                packages=pkg,
                artifacts={self._artifacts["virtual_env"]["default"]},
            )


def _vers(s: dict) -> str:
    # TODO: this may be useful elsewhere
    if s.get("version"):
        return f" =={s.get('version')}"
    return ""
