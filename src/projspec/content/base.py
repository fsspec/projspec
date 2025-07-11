from dataclasses import dataclass, field

from projspec.artifact import BaseArtifact
from projspec.proj.base import Project
from projspec.utils import Enum


@dataclass
class BaseContent:
    proj: Project = field(repr=False)
    artifacts: set[BaseArtifact] = field(repr=False)

    def _repr2(self):
        return {
            k: (v.name if isinstance(v, Enum) else v)
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in ("proj", "artifacts")
        }
