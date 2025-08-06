from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class PythonPackage(BaseContent):
    package_name: str


@dataclass
class Pyproject(PythonPackage):
    """Usually a pyproject.toml file"""

    meta: str


@dataclass
class Cargo(PythonPackage):
    """Usually a Cargo.toml file"""

    meta: str


@dataclass
class CondaRecipe(PythonPackage):
    """usually from a meta.yaml file"""

    meta: str


@dataclass
class NodePackage(BaseContent):
    """Usually a package.json file"""

    package_name: str
