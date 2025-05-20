from dataclasses import dataclass
import enum
from projspec.content import BaseContent


class Stack(enum.Enum):
    """The type of environment"""
    PIP = "pip"
    CONDA = "conda"


class Precision(enum.Enum):
    SPEC = "spec"
    LOCK = "lock"


@dataclass
class Environment(BaseContent):
    """Definition of a python runtime environment"""
    stack: Stack
    precision: Precision
    packages: list[str]
