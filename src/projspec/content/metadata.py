from dataclasses import dataclass, field
import re

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
    """A legal description of what the given project (code and other assets) can be used for.

    This could be one of the typical open-source permissive licenses (see https://spdx.org/licenses/),
    specified either just by its name or by a link. Some projects will have custom or restrictive
    conditions on their replication and use.
    """

    # https://opensource.org/licenses

    shortname: str = field(default="unknown")  # aka SPDX
    fullname: str = field(default="unknown")
    url: str = field(default="")  # relative in the project or remote HTTP


class Licensed(ProjectExtra):
    """A license for the repo, as an isolated top-level text file"""

    pattern = re.compile(r"LICEN[SC]E($|([.].*))", re.IGNORECASE)  # COPYING?
    lic_file: str

    def match(self):
        try:
            self.lic_file = next(
                iter(_ for _ in self.proj.basenames if self.pattern.match(_))
            )
        except StopIteration:
            return False
        return True

    def parse(self) -> None:
        # figure out how to get the name from the file
        # TODO: read and match first line of license file
        text = self.proj.fs.open(self.proj.basenames[self.lic_file], "rt").read()
        lic = None
        for k, v in known.items():
            if re.search(k, text):
                lic = License(
                    proj=self.proj,
                    shortname=v[0],
                    fullname=v[1] or k,
                    url=f"https://spdx.org/licenses/{v[0]}.html",
                )
                break
        self._contents["license"] = lic or License(proj=self.proj, url=self.lic_file)


# could embed https://spdx.org/licenses/licenses.json , 330kB
# search: (shortname, fullname)
# if fullname is None, same as search
known = {
    # many variants of this
    "GNU GENERAL PUBLIC LICENSE.*Version 3": (
        "GPL-3.0-or-later",
        "GNU General Public License v3.0 or later",
    ),
    # few variants
    "GNU LESSER GENERAL PUBLIC LICENSE.*Version 3": (
        "LGPL-3.0+",
        "GNU Lesser General Public License v3.0 or later",
    ),
    # also 1-clause and 2-clause listed
    "BSD 3-Clause License": ("BSD-3-Clause", None),
    "MIT License": ("MIT", None),
    # also v1.0 and v1.1 listed
    "Apache License.*Version 2.0": ("Apache-2.0", "Apache License 2.0"),
}
