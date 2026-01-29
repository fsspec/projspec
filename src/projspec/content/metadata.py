from dataclasses import dataclass, field

from projspec.content import BaseContent
from projspec.proj.base import ProjectExtra


@dataclass
class DescriptiveMetadata(BaseContent):
    """Miscellaneous descriptive information

    Typically includes authors, tags, and text.
    """

    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class License(BaseContent):
    """Project license, with copying permissions and limitations"""

    name: str


class Licensed(ProjectExtra):
    """A Dockerfile in a project directory, which defines how to build an image."""

    def match(self):
        return "LICENSE" in [_.split(".", 1)[0].upper() for _ in self.proj.basenames]

    def parse(self) -> None:
        # figure out how to get the name from the file
        self._contents["license"] = License(proj=self.proj, name="", artifacts=set())
