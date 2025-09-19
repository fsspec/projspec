"""Python runtimes

Note that for actually running python processes. There is also an implicit
runtime from either the env that the process is running in (i.e., the PATH),
or sys.executable.
"""

import json
import subprocess
from functools import cache

from projspec.artifact import FileArtifact


class CondaEnv(FileArtifact):
    """Path to a project conda-built env

    Contains both python itself and any other binaries, as well as linked
    libraries.

    In the case of a project having an environment.yaml with a named output,
    the path may be outside the project tree.
    """

    @staticmethod
    @cache
    def envs() -> list[str]:
        """Global conda env root paths"""
        # pixi also has global envs
        out = subprocess.check_output(["conda", "env", "list", "--json"])
        return json.loads(out.decode())["envs"]


class VirtualEnv(FileArtifact):
    """Path to a project virtual environment

    Some tools like pipenv put these environments in a global location.
    """


class EnvPack(FileArtifact):
    """Archival form of a python environment

    - conda-pack: https://conda.github.io/conda-pack/
    - pixi-pack: https://pixi.sh/latest/deployment/pixi_pack/
    """


class LockFile(FileArtifact):
    """File containing exact environment specification"""
