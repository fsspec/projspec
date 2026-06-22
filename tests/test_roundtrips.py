import os.path
import pytest

import projspec.proj
from projspec.utils import get_cls


@pytest.mark.parametrize(
    "cls_name",
    [
        "django",
        "git_repo",
        "streamlit",
        "python_code",
        "python_library",
        "JLabExtension",
        "IntakeCatalog",
        "DataPackage",
        "PyScript",
        "marimo",
        "flask",
        "dash",
        "panel",
        "Golang",
        "HuggingFaceRepo",
        "HuggingFaceDataset",
        "uv_script",
        "MLFlow",
        "Rust",
        "RustPython",
        "pixi",
        "uv",
        "briefcase",
        "conda_project",
        "conda_workspace",
        "helm_chart",
        "MDBook",
        "RTD",
        "BackstageCatalog",
        "KnowledgeCatalog",
        # CI/CD — file-only _create()
        "GitHubActions",
        "GitLabCI",
        "CircleCI",
        "Taskfile",
        "JustFile",
        "Tox",
        # Data / ML workflows — file-only _create()
        "Dbt",
        "Quarto",
        "Nox",
        "CroissantDataset",
        # Documentation — file-only _create()
        "MkDocs",
        "Sphinx",
        # Infrastructure — file-only _create()
        "DockerCompose",
        "Terraform",
        "Ansible",
        "Pulumi",
        "CDK",
        "Earthfile",
        "Nixpacks",
        "Vagrant",
    ],
)
def test_compliant(tmpdir, cls_name):
    path = str(tmpdir)
    cls = get_cls(cls_name)
    proj = projspec.Project(path)
    files = proj.create(cls_name)
    assert os.path.exists(files[0])
    if not issubclass(cls, projspec.proj.ProjectExtra):
        assert cls_name in proj
    else:
        cls(proj).parse()


def test_cant_create(tmpdir):
    path = str(tmpdir)
    with pytest.raises(NotImplementedError):
        projspec.proj.ProjectSpec.create(path)
