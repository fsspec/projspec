import os

import toml

from projspec.proj import ParseFailed, ProjectSpec
from projspec.proj.pixi import envs_from_lock, extract_tasks
from projspec.utils import AttrDict, PickleableTomlDecoder


class CondaWorkspace(ProjectSpec):
    """A workspace managed by conda-workspaces (``conda.toml``).

    conda-workspaces brings multi-environment workspace management and
    task execution to the conda CLI as a plugin (``conda workspace`` /
    ``conda task``).  The manifest is a conda-native sibling of
    pixi.toml; the lockfile (``conda.lock``) is rattler-lock v6 with
    a ``version: 1`` byte identifying it as conda-workspaces-owned.
    """

    icon = "🧰"
    spec_doc = (
        "https://conda-incubator.github.io/conda-workspaces/reference/conda-toml-spec/"
    )

    def _load_meta(self) -> dict:
        """Merge metadata from ``pyproject.toml`` (``[tool.conda]``) and ``conda.toml``.

        ``conda.toml`` wins on overlap, mirroring conda-workspaces' own
        precedence rule.
        """
        meta = self.proj.pyproject.get("tool", {}).get("conda", {})
        if "conda.toml" in self.proj.basenames:
            try:
                with self.proj.fs.open(self.proj.basenames["conda.toml"], "rb") as f:
                    meta = {
                        **meta,
                        **toml.loads(
                            f.read().decode(), decoder=PickleableTomlDecoder()
                        ),
                    }
            except (OSError, ValueError, UnicodeDecodeError, FileNotFoundError):
                pass
        return meta

    def match(self) -> bool:
        # A bare conda.toml without [workspace] is permitted by the spec
        # as a tasks-only manifest; it does not constitute a workspace
        # on its own, so do not match it here.
        return bool(self._load_meta().get("workspace"))

    def parse(self) -> None:
        from projspec.artifact.python_env import CondaEnv, LockFile
        from projspec.content.environment import Environment, Precision, Stack

        meta = self._load_meta()
        if not meta.get("workspace"):
            raise ParseFailed

        arts = AttrDict()
        conts = AttrDict()
        procs = AttrDict()
        commands = AttrDict()

        run_cmd = ("conda", "task", "run")
        env_flag = "-e"

        extract_tasks(meta, procs, commands, self.proj, run_cmd=run_cmd, env_flag=env_flag)
        if "environments" in meta and "feature" in meta:
            for env_name, details in meta["environments"].items():
                feat: dict = {}
                feats = set(
                    details if isinstance(details, list) else details["features"]
                )
                for fname in feats:
                    feat.update(meta["feature"].get(fname, {}))
                if isinstance(details, list) or not details.get("no-default-feature"):
                    feat.update(meta)
                extract_tasks(
                    feat,
                    procs,
                    commands,
                    self.proj,
                    env=env_name,
                    run_cmd=run_cmd,
                    env_flag=env_flag,
                )

        if procs:
            arts["process"] = procs
        if commands:
            conts["commands"] = commands

        # `envs-dir` is in the conda.toml spec but conda-workspaces' own
        # parser does not yet read it from TOML (uses the model default).
        # Reading it here keeps projspec aligned with the published spec.
        envs_dir = meta.get("workspace", {}).get("envs-dir", ".conda/envs")
        if "conda.lock" in self.proj.basenames:
            conts["environments"] = AttrDict()
            arts["conda_env"] = AttrDict()
            with self.proj.fs.open(self.proj.basenames["conda.lock"], "rb") as f:
                lock_envs = envs_from_lock(f)
            for env_name, details in lock_envs.items():
                arts["conda_env"][env_name] = CondaEnv(
                    proj=self.proj,
                    fn=f"{self.proj.url}/{envs_dir}/{env_name}",
                    cmd=["conda", "workspace", "install", "-e", env_name],
                )
                conts["environments"][env_name] = Environment(
                    proj=self.proj,
                    packages=details["packages"],
                    stack=Stack.CONDA,
                    precision=Precision.LOCK,
                    channels=details["channels"],
                )

        arts["lock_file"] = LockFile(
            proj=self.proj,
            fn=f"{self.proj.url}/conda.lock",
            cmd=["conda", "workspace", "lock"],
        )

        self._artifacts = arts
        self._contents = conts

    @staticmethod
    def _create(path: str) -> None:
        name = os.path.basename(path)
        with open(f"{path}/conda.toml", "wt") as f:
            f.write(
                f"""[workspace]
name = "{name}"
channels = ["conda-forge"]
platforms = ["osx-arm64", "linux-64", "win-64"]
version = "0.1.0"

[tasks]
hello = "echo 'hello world'"

[dependencies]
python = ">=3.10"
"""
            )
