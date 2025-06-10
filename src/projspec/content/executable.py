"""Executable contents produce artifacts"""

from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class Command(BaseContent):
    """The simplest runnable thing - we don't know what it does"""

    cmd: list[str]
    background: bool = False
    interactive: bool = False
