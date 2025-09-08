from dataclasses import dataclass

from projspec.content import BaseContent


@dataclass
class PythonPackage(BaseContent):
    """Importable python directory, i.e., containing an __init__.py file."""

    package_name: str
