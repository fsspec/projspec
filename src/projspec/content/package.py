from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class PythonPackage(BaseContent):
    """Importable python directory, i.e., containing an __init__.py file."""

    package_name: str


@dataclass
class RustModule(BaseContent):
    """Usually a directory with a Cargo.toml file"""

    name: str


@dataclass
class NodePackage(BaseContent):
    """Buildable nodeJS source"""

    name: str
