import toml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict

# pixi supports extensions, e.g., ``pixi global install``
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
    """Name of current platform as a conda channel"""
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

    pixi is a conda-stack project-oriented (aka "workspace") env and execution manager
    """

    # some example projects:
    # https://github.com/prefix-dev/pixi/tree/main/examples
    # spec docs
    # https://pixi.sh/dev/reference/pixi_manifest/

    def match(self) -> bool:
        meta = self.root.pyproject.get("tools", {}).get("pixi", {})
        basenames = (_.rsplit("/", 1)[-1] for _ in self.root.filelist)
        return bool(meta) or "pixi.toml" in basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        meta = self.root.pyproject.get("tools", {}).get("pixi", {})
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in self.root.filelist}
        if "pixi.toml" in basenames:
            try:
                with self.root.fs.open(basenames["pixi.toml"], "rb") as f:
                    meta.update(toml.loads(f.read().decode()))
            except (OSError, ValueError, UnicodeDecodeError):
                pass
        if not meta:
            raise ValueError

        arts = AttrDict()
        conts = AttrDict()

        # Can categorize metadata into "features", each of which is an independednt
        # set of deps, tasks etc. However, project may have only one such,
        # the implicit "default" feature. Often, environments map to features.

        # target.*.activation run when starting an env for given platform
        procs = AttrDict()
        commands = AttrDict()
        for name, task in meta.get("tasks", {}).items():
            cmd = task["cmd"] if isinstance(task, dict) else task
            # NB: these may have dependencies on other tasks and envs, but pixi
            # manages those
            art = Process(proj=self.root, cmd=["pixi", "run", name])
            procs[name] = art
            commands[name] = Command(proj=self.root, artifacts={art}, cmd=cmd)
        for platform, v in meta.get("target", {}).items():
            for name, task in v.get("tasks", {}).items():
                cmd = task["cmd"] if isinstance(task, dict) else task
                commands[name] = Command(
                    proj=self.root, artifacts=set(), cmd=cmd
                )
                if platform == this_platform():
                    # only commands on current platform can be executed
                    procs[name] = Process(
                        proj=self.root, cmd=["pixi", "run", name]
                    )
                    commands[name].artifacts.add(art)

        if procs:
            arts["process"] = procs
        if commands:
            conts["commands"] = commands

        # TODO: (python) environments, pixi.lock environment(s)

        # Any environment can be packed if we have access to pixi-pack

        # If there is a "package" section, project can build to a .conda/.whl
        # Env vars are defined in activation.env .

        # pixi supports conda/pypi split envs with [pypi-dependencies], which
        # can include local paths, git, URL
        # https://pixi.sh/v0.35.0/reference/project_configuration/#full-specification

        # pixi also allows for building sub-packages by including them in
        # package.run-dependencies with local or remote paths. In such cases,
        # we can know of projects in the tree without walking the directory.

        self._artifacts = arts
        self._contents = conts
