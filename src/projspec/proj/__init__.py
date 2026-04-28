"""Project and spec classes"""

from projspec.proj.base import ParseFailed, Project, ProjectSpec, ProjectExtra

from projspec.proj.ai import AIEnabled
from projspec.proj.backstage import BackstageCatalog
from projspec.proj.briefcase import Briefcase
from projspec.proj.cicd import (
    CircleCI,
    GitHubActions,
    GitLabCI,
    JustFile,
    Taskfile,
    Tox,
)
from projspec.proj.conda_package import CondaRecipe, RattlerRecipe
from projspec.proj.conda_project import CondaProject
from projspec.proj.data_dir import Data
from projspec.proj.datapackage import DataPackage, DVCRepo
from projspec.proj.dataworkflows import (
    Airflow,
    Dagster,
    Dbt,
    Kedro,
    Metaflow,
    MLFlow,
    Nox,
    Prefect,
    Quarto,
    Snakemake,
)
from projspec.proj.documentation import RTD, MDBook, MkDocs, Sphinx, Docusaurus
from projspec.proj.git import GitRepo
from projspec.proj.golang import Golang
from projspec.proj.helm import HelmChart
from projspec.proj.hf import HuggingFaceRepo
from projspec.proj.ide import JetbrainsIDE, NvidiaAIWorkbench, VSCode
from projspec.proj.infra import (
    Ansible,
    CDK,
    DockerCompose,
    Earthfile,
    Nixpacks,
    Pulumi,
    Terraform,
    Vagrant,
)
from projspec.proj.jsframeworks import (
    Bun,
    Deno,
    NextJS,
    NuxtJS,
    Pnpm,
    SvelteKit,
    Vite,
)
from projspec.proj.node import JLabExtension, Node, Yarn
from projspec.proj.pixi import Pixi
from projspec.proj.poetry import Poetry
from projspec.proj.published import Cited, Zenodo
from projspec.proj.pyscript import PyScript
from projspec.proj.python_code import PythonCode, PythonLibrary
from projspec.proj.rust import Rust, RustPython
from projspec.proj.uv import Uv
from projspec.proj.webapp import Django, Gradio, Marimo, Shiny, Streamlit

__all__ = [
    "ParseFailed",
    "Project",
    "ProjectSpec",
    # CI/CD
    "CircleCI",
    "GitHubActions",
    "GitLabCI",
    "JustFile",
    "Taskfile",
    "Tox",
    # Conda
    "CondaRecipe",
    "CondaProject",
    # Data
    "Data",
    "DataPackage",
    "DVCRepo",
    # Data/ML workflows
    "Airflow",
    "Dagster",
    "Dbt",
    "Kedro",
    "Metaflow",
    "MLFlow",
    "Nox",
    "Prefect",
    "Quarto",
    "Snakemake",
    # Documentation
    "Docusaurus",
    "MkDocs",
    "MDBook",
    "RTD",
    "Sphinx",
    # Git
    "GitRepo",
    # Go
    "Golang",
    # Helm/K8s
    "HelmChart",
    # HuggingFace
    "HuggingFaceRepo",
    # IDE
    "AIEnabled",
    "BackstageCatalog",
    "Briefcase",
    "Cited",
    "Zenodo",
    "JetbrainsIDE",
    "NvidiaAIWorkbench",
    "VSCode",
    # Infrastructure
    "Ansible",
    "CDK",
    "DockerCompose",
    "Earthfile",
    "Nixpacks",
    "Pulumi",
    "Terraform",
    "Vagrant",
    # JavaScript frameworks
    "Bun",
    "Deno",
    "NextJS",
    "NuxtJS",
    "Pnpm",
    "SvelteKit",
    "Vite",
    # Node
    "JLabExtension",
    "Node",
    "Yarn",
    # Python packaging
    "Pixi",
    "Poetry",
    "PyScript",
    "PythonCode",
    "PythonLibrary",
    "Uv",
    # Rust
    "Rust",
    "RustPython",
    # Web apps
    "Django",
    "Gradio",
    "Marimo",
    "Shiny",
    "Streamlit",
]
