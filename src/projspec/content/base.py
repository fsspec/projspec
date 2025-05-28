from dataclasses import dataclass, field

from projspec.artifact import BaseArtifact
from projspec.proj.base import ProjectSpec


@dataclass
class BaseContent:
    proj: ProjectSpec = field(repr=False)
    artifacts: set[BaseArtifact] = field(repr=False)
