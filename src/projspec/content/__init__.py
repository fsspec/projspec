"""Contents classes - information declared in project specs"""

from projspec.content.base import BaseContent
from projspec.content.cicd import (
    CIWorkflow,
    GithubAction,
    PipelineStage,
    ServiceDependency,
)
from projspec.content.data import (
    Dataset,
    FrictionlessData,
    IntakeSource,
    TabularData,
)
from projspec.content.env_var import EnvironmentVariables
from projspec.content.environment import Environment, Stack, Precision
from projspec.content.executable import Command
from projspec.content.metadata import Citation, DescriptiveMetadata, License
from projspec.content.package import PythonPackage
from projspec.content.vcs import VCSInfo


__all__ = [
    "BaseContent",
    "CIWorkflow",
    "GithubAction",
    "PipelineStage",
    "ServiceDependency",
    "Dataset",
    "FrictionlessData",
    "IntakeSource",
    "TabularData",
    "EnvironmentVariables",
    "Command",
    "Citation",
    "License",
    "DescriptiveMetadata",
    "PythonPackage",
    "Environment",
    "Stack",
    "Precision",
    "VCSInfo",
]
