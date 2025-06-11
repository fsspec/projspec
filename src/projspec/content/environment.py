from dataclasses import dataclass
from enum import auto

from projspec.content import BaseContent
from projspec.utils import Enum


class Stack(Enum):
    """The type of environment"""

    PIP = auto()
    CONDA = auto()


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
