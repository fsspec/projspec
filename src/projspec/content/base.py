from dataclasses import dataclass

from projspec.artifact import BaseArtifact


@dataclass
class BaseContent:
    artifact: BaseArtifact | None
