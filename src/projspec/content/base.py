from dataclasses import dataclass, field

from projspec.artifact import BaseArtifact
from projspec.proj.base import Project


@dataclass
class BaseContent:
    proj: Project = field(repr=False)
    artifacts: set[BaseArtifact] = field(repr=False)
