import toml

from projspec.proj import ParseFailed, ProjectSpec
from projspec.utils import AttrDict, PickleableTomlDecoder

# pixi supports extensions, e.g., ``pixi global install``,
# which is how you get access to pixi-pack, for instance.

# https://github.com/conda/conda/blob/main/conda/base/context.py
_platform_map = {
    "freebsd13": "freebsd",
    "linux2": "linux",
    "linux": "linux",
    "darwin": "osx",
    "win32": "win",
    "zos": "zos",
}
non_x86_machines = {
    "armv6l",
    "armv7l",
    "aarch64",
    "arm64",
    "ppc64",
    "ppc64le",
    "riscv64",
    "s390x",
}
_arch_names = {
    32: "x86",
    64: "x86_64",
}


def this_platform():
    """Name of the current platform as a conda channel"""
    import platform
    import struct
    import sys

    base = _platform_map.get(sys.platform, "unknown")
    bits = 8 * struct.calcsize("P")
    m = platform.machine()
    platform = m if m in non_x86_machines else _arch_names[bits]
    return f"{base}-{platform}"


class Pixi(ProjectSpec):
    """A project using https://pixi.sh/

    pixi is a conda-stack, project-oriented (aka "workspace") env and execution manager.
    """

    spec_doc = "https://pixi.sh/latest/reference/pixi_manifest"

    # some example projects:
    # https://github.com/prefix-dev/pixi/tree/main/examples
    # spec docs
    # https://pixi.sh/dev/reference/pixi_manifest/

    def match(self) -> bool:
        meta = self.proj.pyproject.get("tools", {}).get("pixi", {})
        return bool(meta) or "pixi.toml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.installable import CondaPackage
        from projspec.artifact.python_env import CondaEnv, LockFile
        from projspec.content.environment import Environment, Precision, Stack

        meta = self.proj.pyproject.get("tools", {}).get("pixi", {})
        if "pixi.toml" in self.proj.basenames:
            try:
                with self.proj.fs.open(self.proj.basenames["pixi.toml"], "rb") as f:
                    meta.update(
                        toml.loads(f.read().decode(), decoder=PickleableTomlDecoder())
                    )
            except (OSError, ValueError, UnicodeDecodeError, FileNotFoundError):
                pass
        if not meta:
            raise ParseFailed

        arts = AttrDict()
        conts = AttrDict()

        # Can categorize metadata into "features", each of which is an independent
        # set of deps, tasks ,etc. However, projects may have only one,
        # the implicit "default" feature. Often, environments map to features.

        # target.*.activation run when starting an env for given platform
        procs = AttrDict()
        commands = AttrDict()
        extract_feature(meta, procs, commands, self)
        if "environments" in meta and "feature" in meta:
            for env_name, details in meta["environments"].items():
                feat = {}
                feats = set(
                    details if isinstance(details, list) else details["features"]
                )
                for feat_name in feats:
                    feat.update(meta["feature"][feat_name])
                if isinstance(details, list) or not details.get("no-default-feature"):
                    feat.update(meta)
                extract_feature(feat, procs, commands, self, env=env_name)

        if procs:
            arts["process"] = procs
        if commands:
            conts["commands"] = commands

        if "pixi.lock" in self.proj.basenames:
            conts["environments"] = AttrDict()
            arts["conda_env"] = AttrDict()
            with self.proj.fs.open(self.proj.basenames["pixi.lock"], "rb") as f:
                lock_envs = envs_from_lock(f)
            for env_name, details in lock_envs.items():
                art = CondaEnv(
                    proj=self.proj,
                    fn=f"{self.proj.url}/.pixi/envs/{env_name}",
                    cmd=["pixi", "install", "-e", env_name],
                )
                arts["conda_env"][env_name] = art
                conts["environments"][env_name] = Environment(
                    proj=self.proj,
                    packages=details["packages"],
                    artifacts={art},
                    stack=Stack.CONDA,
                    precision=Precision.LOCK,
                    channels=details["channels"],
                )
        arts["lock_file"] = LockFile(
            proj=self.proj,
            fn=f"{self.proj.url}/pixi.lock",
            cmd=["pixi", "lock"],
        )

        if pkg := meta.get("package", {}):
            arts["conda_package"] = CondaPackage(
                proj=self.proj,
                name=pkg["name"],
                fn=f"{pkg['name']}-{pkg['version']}*.conda",
                cmd=["pixi", "build"],
            )

        # Any environment can be packed if we have access to pixi-pack; this currently (v0.6.5)
        # fails if there is any source-install in the env, which there normally is!

        # pixi supports conda/pypi split envs with [pypi-dependencies], which
        # can include local paths, git, URL
        # <https://pixi.sh/latest/reference/project_configuration/#full-specification>.

        # Pixi also allows for requiring sub-packages by including them in
        # package.run-dependencies with local or remote paths. In such cases,
        # we can know of projects in the tree without walking the directory.

        # environments built by pixi will contain a conda-meta/pixi file with the meta file,
        # pixi version, and lockfile hash detailed.

        self._artifacts = arts
        self._contents = conts


def extract_feature(
    meta: dict,
    procs: AttrDict,
    commands: AttrDict,
    pixi: Pixi,
    env: str | None = None,
):
    """Consolidate metadata from 'features' to create commands and processes"""
    from projspec.artifact.process import Process
    from projspec.content.executable import Command

    for name, task in meta.get("tasks", {}).items():
        if env:
            name = f"{name}.{env}"
        cmd = ["pixi", "run", name]
        if env:
            cmd.extend(["--environment", env])
        art = Process(proj=pixi.proj, cmd=cmd)
        procs[name] = art
        # tasks without a command are aliases
        cmd = task.get("cmd", "") if isinstance(task, dict) else task
        # NB: these may have dependencies on other tasks and envs, but pixi
        # manages those.
        commands[name] = Command(proj=pixi.proj, artifacts={art}, cmd=cmd)
    for platform, v in meta.get("target", {}).items():
        for name, task in v.get("tasks", {}).items():
            if env:
                name = f"{name}.{env}"
            cmd = task["cmd"] if isinstance(task, dict) else task
            commands[name] = Command(proj=pixi.proj, artifacts=set(), cmd=cmd)
            if platform == this_platform():
                # only commands on the current platform can be executed
                cmd = ["pixi", "run", name]
                if env:
                    cmd.extend(["--environment", env])
                art = Process(proj=pixi.proj, cmd=cmd)
                procs[name] = art
                commands[name].artifacts.add(art)


def envs_from_lock(infile) -> dict:
    """Extract the environments info from a pixi (yaml) lock file"""
    # Developed for pixi format format 6
    import yaml

    data = yaml.safe_load(infile)
    pkgs = {}
    for pkg in data["packages"]:
        # TODO: include build/hashes in conda explicit format?
        if "conda" in pkg:
            basename = pkg["conda"].rsplit("/", 1)[-1]
            name, version, _hash = basename.rsplit("-", 2)
            pkgs[pkg["conda"]] = f"{name} =={version}"
        else:
            pkgs[pkg["pypi"]] = f"{pkg['name']} =={pkg['version']}"
    out = {}
    for env_name, env in data["environments"].items():
        req = {
            "packages": [
                pkgs[entry.get("conda", entry.get("pypi"))]
                for entry in next(iter(env["packages"].values()))
            ],
            "channels": [
                _ if isinstance(_, str) else _.get("url", "") for _ in env["channels"]
            ]
            + env.get("indexes", []),
        }
        out[env_name] = req
    return out
