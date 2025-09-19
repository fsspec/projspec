"""Executable contents produce artifacts"""

from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class Command(BaseContent):
    """The simplest runnable thing; we don't know what it does/outputs."""

    cmd: list[str] | str

    def _repr2(self):
        return " ".join(self.cmd) if isinstance(self.cmd, list) else self.cmd
