import toml

import fsspec

from projspec.proj.base import ParseFailed, Project, ProjectSpec
from projspec.proj.python_code import PythonLibrary
from projspec.utils import AttrDict, PickleableTomlDecoder, deep_get


def _parse_conf(self: ProjectSpec, conf: dict | None = None):
    from projspec.artifact.installable import Wheel
    from projspec.artifact.python_env import LockFile, VirtualEnv

    # TODO, uv conf specific env modifiers:
    #  python== from dependency-groups.requires-python
    #  remove deps in exclude-dependencies
    #  add deps in dev-dependencies to "dev"
    #  swap out deps in override-dependencies in all envs
    #  process sources
    #  add index URL, pip.indexurl, info to env channels

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
    else:
        self._artifacts.pop("wheel", None)


class UvScript(PythonLibrary):
    """Single-file project runnable by UV as a script

    Metadata are declared inline in the script header
    """

    spec_doc = "https://docs.astral.sh/uv/guides/scripts/"

    def match(self):
        # this is a file, not a directory
        return any(_.endswith(".py") for _ in self.proj.scanned_files) or (
            self.proj.url.endswith((".py", ".pyw"))
        )

    def parse(self):
        from projspec.artifact.process import Process
        from projspec.content.environment import Environment, Stack, Precision
        from projspec.artifact import LockFile

        found = False
        if self.proj.url.endswith(".py"):
            with self.proj.fs.open(self.proj.url, "rb") as f:
                scanned = {self.proj.url.rsplit("/", 1)[-1][:-3]: f.read()}
                script = True
        else:
            scanned = self.proj.scanned_files
            script = False
        for name, contents in scanned.items():
            if not name.endswith(".py"):
                continue
            try:
                # TODO: optional lockfile is in <name>.lock
                txt = contents.decode()
                lines = txt.split("# /// script", 1)[-1].split("# ///", 1)[0]
                lines = "\n".join(_.removeprefix("# ") for _ in lines.splitlines())
                meta = toml.loads(lines, decoder=PickleableTomlDecoder())
                if "dependencies" not in meta:
                    raise ParseFailed
                # only one env allowed here, but other uv-specific configs may be allowed
                # as in _parse_conf()
                url = self.proj.url if script else f"{self.proj.url}/{name}"
                self.artifacts.setdefault("lockfile", AttrDict())[name[:-3]] = LockFile(
                    proj=self.proj,
                    cmd=["uv", "lock", "--script", name],
                    fn=f"{url}.lock",
                )
                if isinstance(
                    self.proj.fs,
                    (
                        fsspec.implementations.local.LocalFileSystem,
                        fsspec.implementations.http.HTTPFileSystem,
                    ),
                ):
                    self.artifacts.setdefault("process", AttrDict())[
                        name[:-3]
                    ] = Process(proj=self.proj, cmd=["uv", "run", "--script", url])
                packages = meta["dependencies"]
                if ver := meta.get("requires-python"):
                    packages.append(f"python {ver}")
                self.contents.setdefault("environment", AttrDict())[
                    name[:-3]
                ] = Environment(
                    proj=self.proj,
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                    packages=packages,
                    artifacts=set(),
                    channels=deep_get(meta, "tools.uv.index", default=[]),
                )
                found = True
            except (KeyError, ValueError):
                pass
        if not found:
            raise ParseFailed("No python file found")

    @staticmethod
    def _create(path):
        # uv init --script example.py --python 3.12
        with open(f"{path}/example.py", "wt") as f:
            f.write(
                """
# https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies
# /// script
# dependencies = [
#   "requests<3",
#   "rich",
# ]
# ///

import requests
from rich.pretty import pprint

resp = requests.get("https://peps.python.org/api/peps.json")
data = resp.json()
pprint([(k, v["title"]) for k, v in data.items()][:10])
"""
            )


class Uv(PythonLibrary):
    """UV-runnable project

    Note: uv can run any python project, but this tests for uv-specific
    config.
    """

    spec_doc = "https://docs.astral.sh/uv/concepts/configuration-files/"

    def match(self):
        if not {"uv.lock", "uv.toml", ".python-version"}.isdisjoint(
            self.proj.basenames
        ):
            return True
        if "uv" in self.proj.pyproject.get("tools", {}):
            # even if it is present, uv can be explicitly directed to ignore the
            # project https://docs.astral.sh/uv/reference/settings/#managed
            return self.proj.pyproject.get["tool"]["uv"].get("managed", True)
        if (
            self.proj.pyproject.get("build-system", {}).get("build-backend", "")
            == "uv_build"
        ):
            return True
        if ".venv" in self.proj.basenames:
            try:
                with self.proj.fs.open(f"{self.proj.url}/.venv/pyvenv.cfg", "rt") as f:
                    txt = f.read()
                return "uv =" in txt
            except (OSError, FileNotFoundError):
                pass
        return False

    def parse(self):
        from projspec.content.environment import Environment, Precision, Stack

        super().parse()
        meta = self.proj.pyproject
        conf = meta.get("tools", {}).get("uv", {})
        try:
            with self.get_file("uv.toml") as f:
                conf2 = toml.load(f, decoder=PickleableTomlDecoder())
        except (OSError, FileNotFoundError):
            conf2 = {}
        conf.update(conf2)
        try:
            with self.get_file("uv.lock") as f:
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
