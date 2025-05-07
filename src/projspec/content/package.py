from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class PythonPackage(BaseContent):
    package_name: str
    # TODO: maybe contained modules/packages, but probably not
