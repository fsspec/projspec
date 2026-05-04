"""Tests for the CondaWorkspace project spec.

Mirrors the structure used in ``test_new_specs.py``: ``write_files``
seeds a tmpdir, ``raw_spec`` constructs the spec bypassing
``__init__``'s ``match()`` call so we can assert on ``match()`` and
``parse()`` independently.
"""

import os
import textwrap

import pytest

import projspec
from projspec.proj.base import ParseFailed, registry
from projspec.proj.conda_workspace import CondaWorkspace
from projspec.proj.pixi import Pixi

CONDA_TOML = """\
    [workspace]
    name = "wsdemo"
    channels = ["conda-forge"]
    platforms = ["linux-64", "osx-arm64", "win-64"]

    [dependencies]
    python = ">=3.10"

    [feature.test.dependencies]
    pytest = ">=8.0"

    [environments]
    default = []
    test = { features = ["test"] }

    [tasks]
    hello = "echo hello"
    """


PYPROJECT_TOOL_CONDA = """\
    [project]
    name = "wsdemo-pyproject"
    version = "0.1.0"

    [tool.conda.workspace]
    name = "wsdemo"
    channels = ["conda-forge"]
    platforms = ["linux-64", "osx-arm64"]

    [tool.conda.dependencies]
    python = ">=3.11"

    [tool.conda.tasks]
    greet = "echo hi"
    """


PYPROJECT_TOOL_PIXI_ONLY = """\
    [tool.pixi.workspace]
    name = "pixi-only"
    channels = ["conda-forge"]
    platforms = ["linux-64"]

    [tool.pixi.dependencies]
    python = ">=3.10"
    """


CONDA_TOML_TASKS_ONLY = """\
    [tasks]
    hello = "echo hello"
    """


CONDA_LOCK = """\
    version: 1
    environments:
      default:
        channels:
          - url: https://conda.anaconda.org/conda-forge/
        packages:
          linux-64:
            - conda: https://conda.anaconda.org/conda-forge/noarch/python-3.12.0-h0.conda
    packages:
      - conda: https://conda.anaconda.org/conda-forge/noarch/python-3.12.0-h0.conda
        sha256: deadbeef
    """


def write_files(tmpdir, files: dict[str, str]) -> str:
    path = str(tmpdir)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full) or path, exist_ok=True)
        with open(full, "w") as f:
            f.write(textwrap.dedent(content))
    return path


def make_proj(tmpdir, files: dict[str, str]):
    return projspec.Project(write_files(tmpdir, files))


def raw_spec(cls, proj):
    inst = cls.__new__(cls)
    inst.proj = proj
    inst._contents = None
    inst._artifacts = None
    return inst


class TestMatch:
    @pytest.mark.parametrize(
        "files, expected",
        [
            ({"conda.toml": CONDA_TOML}, True),
            ({"pyproject.toml": PYPROJECT_TOOL_CONDA}, True),
            ({}, False),
            # A bare conda.toml without [workspace] is a tasks-only manifest
            # per the spec; not a workspace on its own.
            ({"conda.toml": CONDA_TOML_TASKS_ONLY}, True),
            # pyproject.toml with only [tool.pixi.workspace] is the Pixi
            # spec's job, not ours.
            ({"pyproject.toml": PYPROJECT_TOOL_PIXI_ONLY}, False),
        ],
        ids=[
            "conda_toml_with_workspace",
            "pyproject_with_tool_conda_workspace",
            "empty_dir",
            "conda_toml_tasks_only",
            "pyproject_pixi_only",
        ],
    )
    def test_match(self, tmpdir, files, expected):
        proj = make_proj(tmpdir, files)
        assert raw_spec(CondaWorkspace, proj).match() is expected


class TestParse:
    @pytest.mark.parametrize(
        "files, task_name",
        [
            ({"conda.toml": CONDA_TOML}, "hello"),
            ({"pyproject.toml": PYPROJECT_TOOL_CONDA}, "greet"),
        ],
        ids=["conda_toml", "pyproject_form"],
    )
    def test_task_registered(self, tmpdir, files, task_name):
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CondaWorkspace, proj)
        spec.parse()

        assert task_name in spec._contents["commands"]
        assert task_name in spec._artifacts["process"]
        assert spec._artifacts["process"][task_name].cmd == [
            "conda",
            "task",
            "run",
            task_name,
        ]

    def test_lock_file_artifact(self, tmpdir):
        proj = make_proj(tmpdir, {"conda.toml": CONDA_TOML})
        spec = raw_spec(CondaWorkspace, proj)
        spec.parse()

        assert spec._artifacts["lock_file"].cmd == ["conda", "workspace", "lock"]
        assert spec._artifacts["lock_file"].fn.endswith("/conda.lock")

    def test_parse_with_lockfile(self, tmpdir):
        proj = make_proj(
            tmpdir,
            {"conda.toml": CONDA_TOML, "conda.lock": CONDA_LOCK},
        )
        spec = raw_spec(CondaWorkspace, proj)
        spec.parse()

        assert "default" in spec._contents["environments"]

        env = spec._artifacts["conda_env"]["default"]
        assert env.cmd == ["conda", "workspace", "install", "-e", "default"]
        assert env.fn.endswith("/.conda/envs/default")

    def test_negative_parse_no_workspace(self, tmpdir):
        proj = make_proj(tmpdir, {"conda.toml": CONDA_TOML_TASKS_ONLY})
        spec = raw_spec(CondaWorkspace, proj)
        with pytest.raises(ParseFailed):
            spec.parse()


class TestRegistration:
    def test_in_proj_registry(self):
        assert "conda_workspace" in registry

    def test_create_writes_conda_toml(self, tmpdir):
        path = str(tmpdir)
        CondaWorkspace._create(path)
        text = open(os.path.join(path, "conda.toml")).read()
        assert "[workspace]" in text
        assert 'channels = ["conda-forge"]' in text


class TestPixiUnchanged:
    """Regression: refactoring pixi.py must not alter Pixi behaviour."""

    PIXI_TOML = """\
        [workspace]
        name = "px"
        channels = ["conda-forge"]
        platforms = ["linux-64"]

        [tasks]
        build = "echo build"
        """

    def test_pixi_match(self, tmpdir):
        proj = make_proj(tmpdir, {"pixi.toml": self.PIXI_TOML})
        assert raw_spec(Pixi, proj).match()

    def test_pixi_task_cmd_unchanged(self, tmpdir):
        proj = make_proj(tmpdir, {"pixi.toml": self.PIXI_TOML})
        spec = raw_spec(Pixi, proj)
        spec.parse()
        assert spec._artifacts["process"]["build"].cmd == ["pixi", "run", "build"]
