"""Contents classes - information declared in project specs"""

from projspec.content.base import BaseContent
from projspec.content.data import TabularData, IntakeSource
from projspec.content.env_var import EnvironmentVariables
from projspec.content.environment import Environment, Stack, Precision
from projspec.content.executable import Command

from projspec.content.metadata import DescriptiveMetadata, License
from projspec.content.package import PythonPackage


__all__ = [
    "BaseContent",
    "TabularData",
    "IntakeSource",
    "EnvironmentVariables",
    "Command",
    "License",
    "DescriptiveMetadata",
    "PythonPackage",
    "Environment",
    "Stack",
    "Precision",
]
