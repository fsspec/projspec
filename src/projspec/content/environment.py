from dataclasses import dataclass, field
from enum import auto

from projspec.content import BaseContent
from projspec.utils import Enum


class Stack(Enum):
    """The type of environment"""

    PIP = auto()
    CONDA = auto()
    NPM = auto()
    YARN = auto()


class Precision(Enum):
    """Type of environment definition"""

    # TODO: categories may be refined
    SPEC = auto()
    LOCK = auto()


@dataclass
class Environment(BaseContent):
    """Definition of a python runtime environment"""

    stack: Stack
    precision: Precision
    packages: list[str]
    # This may be empty for loose specs; may include endpoints or index URLs.
    channels: list[str] = field(default_factory=list)

    def _repr2(self):
        out = {
            k: (v.name if isinstance(v, Enum) else v)
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in ("proj", "artifacts")
        }
        if not self.channels:
            out.pop("channels", None)
        return out

@dataclass
class NodeEnvironment(BaseContent):
    """Definition of a Node.js environment"""

    stack: Stack  # e.g., Stack.NPM, Stack.YARN
    packages: dict[str, str]  # {package: version spec}
    dev_packages: dict[str, str] = field(default_factory=dict)

    def _repr2(self):
        out = {
            "stack": self.stack.name,
            "packages": self.packages,
        }
        if self.dev_packages:
            out["dev_packages"] = self.dev_packages
        return out
