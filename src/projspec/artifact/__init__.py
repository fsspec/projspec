"""Things that a project can do or make"""

from projspec.artifact.base import BaseArtifact, FileArtifact
from projspec.artifact.container import DockerImage
from projspec.artifact.installable import CondaPackage, Wheel
from projspec.artifact.process import Process
from projspec.artifact.python_env import EnvPack, CondaEnv, VirtualEnv, LockFile

__all__ = [
    "BaseArtifact",
    "FileArtifact",
    "DockerImage",
    "CondaPackage",
    "Wheel",
    "Process",
    "EnvPack",
    "CondaEnv",
    "VirtualEnv",
    "LockFile",
]
