from dataclasses import dataclass, field

from projspec.artifact import BaseArtifact
from projspec.proj.base import Project
from projspec.utils import Enum, camel_to_snake

registry = {}


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

    @classmethod
    def __init_subclass__(cls, **kwargs):
        sn = cls.snake_name()
        if sn in registry:
            raise RuntimeError()
        registry[sn] = cls

    @classmethod
    def snake_name(cls):
        return camel_to_snake(cls.__name__)


def get_content_cls(name: str) -> type[BaseContent]:
    """Find a content class by snake-case name."""
    return registry[name]
