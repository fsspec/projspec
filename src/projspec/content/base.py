from dataclasses import dataclass, field

from projspec.artifact import BaseArtifact
from projspec.proj.base import Project
from projspec.utils import Enum, camel_to_snake

registry = {}


@dataclass
class BaseContent:
    """A descriptive piece of information declared in a project

    Content classes tell you something fundamental about a project, but do
    not have any other functionality than to allow introspection. We use
    dataclasses to define what information a given Content subclass should
    provide.
    """

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
        registry[sn] = cls

    @classmethod
    def snake_name(cls):
        return camel_to_snake(cls.__name__)

    def to_dict(self, compact=False):
        if compact:
            return self._repr2()
        dic = {
            k: getattr(self, k)
            for k in self.__dataclass_fields__
            if k not in ("proj", "artifacts")
        }
        dic["artifacts"] = []
        dic["klass"] = ["content", self.snake_name()]
        for k in list(dic):
            if isinstance(dic[k], Enum):
                dic[k] = dic[k].value
        return dic
