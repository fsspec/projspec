"""Tests for new project spec types added in the bulk expansion.

Structure
---------
Each spec family gets one class with:
  - test_match_positive  – the spec IS detected given the right files
  - test_match_negative  – the spec is NOT detected without those files
  - test_parse_contents  – expected content keys are present after parse()
  - test_parse_artifacts – expected artifact keys are present after parse()
  - (where applicable) test_parse_detail – spot-check on specific parsed values

Helper
------
``make_spec(cls, tmpdir, files)`` writes *files* (dict of rel-path → text) into
*tmpdir* and returns a freshly constructed spec instance with _contents and
_artifacts pre-initialised to None (matching the state before parse() is called
by ProjectSpec.__init__).
"""

import json
import os
import textwrap

import pytest
import yaml

import projspec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_files(tmpdir, files: dict[str, str]) -> str:
    """Write *files* into *tmpdir* and return the directory path."""
    path = str(tmpdir)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(textwrap.dedent(content))
    return path


def make_proj(tmpdir, files: dict[str, str]):
    path = write_files(tmpdir, files)
    return projspec.Project(path)


def raw_spec(cls, proj):
    """Instantiate a spec bypassing __init__'s match() call, for manual testing."""
    inst = cls.__new__(cls)
    inst.proj = proj
    inst._contents = None
    inst._artifacts = None
    return inst


# ---------------------------------------------------------------------------
# CI/CD specs
# ---------------------------------------------------------------------------


class TestGitHubActions:
    FILES = {
        ".github/workflows/ci.yml": """\
            name: CI
            on:
              push:
                branches: [main]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import GitHubActions

        assert raw_spec(GitHubActions, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import GitHubActions

        assert not raw_spec(GitHubActions, proj).match()

    def test_parse_contents(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import GitHubActions

        spec = raw_spec(GitHubActions, proj)
        spec.parse()
        assert "ci_workflow" in spec._contents

    def test_parse_detail(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import GitHubActions

        spec = raw_spec(GitHubActions, proj)
        spec.parse()
        wf = list(spec._contents["ci_workflow"].values())[0]
        assert wf.provider == "github"
        assert "test" in wf.jobs
        assert "push" in wf.triggers

    def test_multiple_workflows(self, tmpdir):
        files = dict(self.FILES)
        files[".github/workflows/release.yml"] = textwrap.dedent(
            """\
            name: Release
            on: [push]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps: []
            """
        )
        proj = make_proj(tmpdir, files)
        from projspec.proj.cicd import GitHubActions

        spec = raw_spec(GitHubActions, proj)
        spec.parse()
        assert len(spec._contents["ci_workflow"]) == 2


class TestGitLabCI:
    FILES = {
        ".gitlab-ci.yml": """\
            stages:
              - test
              - deploy
            test:
              stage: test
              script:
                - pytest
            deploy:
              stage: deploy
              script:
                - echo deploy
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import GitLabCI

        assert raw_spec(GitLabCI, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import GitLabCI

        assert not raw_spec(GitLabCI, proj).match()

    def test_parse_contents(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import GitLabCI

        spec = raw_spec(GitLabCI, proj)
        spec.parse()
        wf = spec._contents["ci_workflow"]
        assert wf.provider == "gitlab"
        assert "test" in wf.jobs
        assert "deploy" in wf.jobs
        assert "test" in wf.triggers


class TestCircleCI:
    FILES = {
        ".circleci/config.yml": """\
            version: 2.1
            jobs:
              build:
                docker:
                  - image: cimg/python:3.11
                steps:
                  - checkout
                  - run: pytest
            workflows:
              main:
                jobs:
                  - build
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import CircleCI

        assert raw_spec(CircleCI, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import CircleCI

        assert not raw_spec(CircleCI, proj).match()

    def test_parse_contents(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import CircleCI

        spec = raw_spec(CircleCI, proj)
        spec.parse()
        wf = spec._contents["ci_workflow"]
        assert wf.provider == "circleci"
        assert "build" in wf.jobs


class TestTaskfile:
    FILES = {
        "Taskfile.yml": """\
            version: '3'
            tasks:
              build:
                desc: Build the project
                cmds:
                  - echo building
              test:
                desc: Run tests
                cmds:
                  - pytest
              lint:
                cmds:
                  - ruff check .
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import Taskfile

        assert raw_spec(Taskfile, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import Taskfile

        assert not raw_spec(Taskfile, proj).match()

    def test_match_variant_names(self, tmpdir):
        for name in ("Taskfile.yaml", "taskfile.yml", "taskfile.yaml"):
            proj = make_proj(
                tmpdir, {name: "version: '3'\ntasks:\n  x:\n    cmds: [echo]\n"}
            )
            from projspec.proj.cicd import Taskfile

            assert raw_spec(Taskfile, proj).match(), f"{name} should match"

    def test_parse_contents(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import Taskfile

        spec = raw_spec(Taskfile, proj)
        spec.parse()
        assert "build" in spec._contents["command"]
        assert "test" in spec._contents["command"]
        assert "lint" in spec._contents["command"]

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import Taskfile

        spec = raw_spec(Taskfile, proj)
        spec.parse()
        assert "build" in spec._artifacts["process"]
        assert spec._artifacts["process"]["build"].cmd == ["task", "build"]


class TestJustFile:
    FILES = {
        "justfile": """\
            # Build the project
            build:
                cargo build --release

            # Run tests
            test:
                cargo test

            fmt:
                cargo fmt
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import JustFile

        assert raw_spec(JustFile, proj).match()

    def test_match_Justfile_capitalised(self, tmpdir):
        proj = make_proj(tmpdir, {"Justfile": "build:\n    echo ok\n"})
        from projspec.proj.cicd import JustFile

        assert raw_spec(JustFile, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import JustFile

        assert not raw_spec(JustFile, proj).match()

    def test_parse_recipes(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.cicd import JustFile

        spec = raw_spec(JustFile, proj)
        spec.parse()
        assert "build" in spec._contents["command"]
        assert "test" in spec._contents["command"]
        assert "fmt" in spec._contents["command"]
        assert spec._artifacts["process"]["build"].cmd == ["just", "build"]


class TestTox:
    FILES_INI = {
        "tox.ini": """\
            [tox]
            envlist = py311, py312, lint

            [testenv]
            deps = pytest
            commands = pytest {posargs}

            [testenv:lint]
            deps = ruff
            commands = ruff check .
            """,
    }

    FILES_PYPROJECT = {
        "pyproject.toml": """\
            [tool.tox]
            [tool.tox.env.py311]
            commands = [["pytest"]]
            [tool.tox.env.lint]
            commands = [["ruff", "check", "."]]
            """,
    }

    def test_match_tox_ini(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_INI)
        from projspec.proj.cicd import Tox

        assert raw_spec(Tox, proj).match()

    def test_match_pyproject(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PYPROJECT)
        from projspec.proj.cicd import Tox

        assert raw_spec(Tox, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.cicd import Tox

        assert not raw_spec(Tox, proj).match()

    def test_parse_envlist(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_INI)
        from projspec.proj.cicd import Tox

        spec = raw_spec(Tox, proj)
        spec.parse()
        assert "py311" in spec._artifacts["process"]
        assert "py312" in spec._artifacts["process"]
        assert "lint" in spec._artifacts["process"]
        assert spec._artifacts["process"]["lint"].cmd == ["tox", "-e", "lint"]

    def test_parse_testenv_sections(self, tmpdir):
        # tox.ini with named [testenv:X] sections but no envlist
        proj = make_proj(tmpdir, {"tox.ini": "[testenv:unit]\ncommands=pytest\n"})
        from projspec.proj.cicd import Tox

        spec = raw_spec(Tox, proj)
        spec.parse()
        assert "unit" in spec._artifacts["process"]

    def test_parse_fallback_generic(self, tmpdir):
        # tox.ini with no envlist and no [testenv:X] sections
        proj = make_proj(tmpdir, {"tox.ini": "[tox]\n"})
        from projspec.proj.cicd import Tox

        spec = raw_spec(Tox, proj)
        spec.parse()
        assert "tox" in spec._artifacts["process"]


# ---------------------------------------------------------------------------
# Data / ML / Workflow specs
# ---------------------------------------------------------------------------


class TestDbt:
    FILES = {
        "dbt_project.yml": """\
            name: 'analytics'
            version: '1.0.0'
            config-version: 2
            profile: 'default'
            model-paths: ['models']
            """,
        "models/example.sql": "SELECT 1 AS id",
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Dbt

        assert raw_spec(Dbt, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Dbt

        assert not raw_spec(Dbt, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Dbt

        spec = raw_spec(Dbt, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["name"] == "analytics"
        assert meta["profile"] == "default"

    def test_parse_standard_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Dbt

        spec = raw_spec(Dbt, proj)
        spec.parse()
        for cmd in ("run", "test", "build", "compile", "seed"):
            assert cmd in spec._contents["command"], f"missing command: {cmd}"
            assert cmd in spec._artifacts["process"], f"missing artifact: {cmd}"

    def test_parse_command_values(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Dbt

        spec = raw_spec(Dbt, proj)
        spec.parse()
        assert spec._contents["command"]["run"].cmd == ["dbt", "run"]
        assert spec._artifacts["process"]["build"].cmd == ["dbt", "build"]


class TestQuarto:
    FILES_PROJECT = {
        "_quarto.yml": """\
            project:
              type: website
              title: My Quarto Site
              output-dir: _site
            format:
              html:
                theme: cosmo
            """,
        "index.qmd": "---\ntitle: Home\n---\nHello!\n",
    }

    FILES_SINGLE_QMD = {
        "report.qmd": "---\ntitle: Report\n---\nContent here.\n",
    }

    def test_match_quarto_yml(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PROJECT)
        from projspec.proj.dataworkflows import Quarto

        assert raw_spec(Quarto, proj).match()

    def test_match_qmd_file(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_SINGLE_QMD)
        from projspec.proj.dataworkflows import Quarto

        assert raw_spec(Quarto, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Quarto

        assert not raw_spec(Quarto, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PROJECT)
        from projspec.proj.dataworkflows import Quarto

        spec = raw_spec(Quarto, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["title"] == "My Quarto Site"

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PROJECT)
        from projspec.proj.dataworkflows import Quarto

        spec = raw_spec(Quarto, proj)
        spec.parse()
        assert "render" in spec._artifacts
        assert "preview" in spec._artifacts
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server

        assert isinstance(spec._artifacts["render"], StaticSite)
        assert isinstance(spec._artifacts["preview"], Server)

    def test_parse_custom_output_dir(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PROJECT)
        from projspec.proj.dataworkflows import Quarto

        spec = raw_spec(Quarto, proj)
        spec.parse()
        assert "_site" in spec._artifacts["render"].fn


class TestNox:
    FILES = {
        "noxfile.py": """\
            import nox

            @nox.session
            def tests(session):
                session.install('pytest')
                session.run('pytest')

            @nox.session(python=['3.11', '3.12'])
            def lint(session):
                session.install('ruff')
                session.run('ruff', 'check', '.')
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Nox

        assert raw_spec(Nox, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Nox

        assert not raw_spec(Nox, proj).match()

    def test_parse_sessions(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Nox

        spec = raw_spec(Nox, proj)
        spec.parse()
        assert "tests" in spec._artifacts["process"]
        assert "lint" in spec._artifacts["process"]
        assert spec._artifacts["process"]["tests"].cmd == ["nox", "-s", "tests"]

    def test_parse_empty_noxfile_fallback(self, tmpdir):
        proj = make_proj(tmpdir, {"noxfile.py": "# no sessions\n"})
        from projspec.proj.dataworkflows import Nox

        spec = raw_spec(Nox, proj)
        spec.parse()
        # Falls back to generic nox command
        assert "nox" in spec._artifacts["process"]


class TestPrefect:
    FILES = {
        "prefect.yaml": """\
            name: my-pipeline
            deployments:
              - name: daily-etl
                entrypoint: flows/etl.py:run_etl
              - name: weekly-report
                entrypoint: flows/report.py:run_report
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Prefect

        assert raw_spec(Prefect, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Prefect

        assert not raw_spec(Prefect, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Prefect

        spec = raw_spec(Prefect, proj)
        spec.parse()
        assert spec._contents["descriptive_metadata"].meta["name"] == "my-pipeline"

    def test_parse_deployments_as_stages(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Prefect

        spec = raw_spec(Prefect, proj)
        spec.parse()
        assert "daily-etl" in spec._contents["pipeline_stage"]
        assert "weekly-report" in spec._contents["pipeline_stage"]

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Prefect

        spec = raw_spec(Prefect, proj)
        spec.parse()
        assert "run" in spec._artifacts["process"]


class TestSnakemake:
    FILES = {
        "Snakefile": """\
            rule all:
                input: "results/output.txt"

            rule process:
                input: "data/input.txt"
                output: "results/output.txt"
                shell: "cat {input} > {output}"

            rule download:
                output: "data/input.txt"
                shell: "echo hello > {output}"
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Snakemake

        assert raw_spec(Snakemake, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Snakemake

        assert not raw_spec(Snakemake, proj).match()

    def test_parse_rules_as_stages(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Snakemake

        spec = raw_spec(Snakemake, proj)
        spec.parse()
        stages = spec._contents.get("pipeline_stage", {})
        # 'all' is filtered out; process and download should appear
        assert "process" in stages
        assert "download" in stages
        assert "all" not in stages

    def test_parse_run_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Snakemake

        spec = raw_spec(Snakemake, proj)
        spec.parse()
        assert "run" in spec._artifacts["process"]
        assert spec._artifacts["process"]["run"].cmd == [
            "snakemake",
            "--cores",
            "all",
        ]


class TestAirflow:
    FILES = {
        "dags/etl_dag.py": """\
            from airflow import DAG
            from airflow.operators.python import PythonOperator

            dag = DAG(dag_id='etl_pipeline', schedule='@daily')
            """,
        "dags/report_dag.py": """\
            from airflow import DAG
            dag = DAG(dag_id='weekly_report', schedule='@weekly')
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Airflow

        assert raw_spec(Airflow, proj).match()

    def test_match_negative_no_dags(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Airflow

        assert not raw_spec(Airflow, proj).match()

    def test_match_negative_empty_dags(self, tmpdir):
        # dags/ exists but no .py files
        os.makedirs(str(tmpdir.join("dags")), exist_ok=True)
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Airflow

        assert not raw_spec(Airflow, proj).match()

    def test_parse_dag_ids_as_stages(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Airflow

        spec = raw_spec(Airflow, proj)
        spec.parse()
        stages = spec._contents.get("pipeline_stage", {})
        assert "etl_pipeline" in stages
        assert "weekly_report" in stages

    def test_parse_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Airflow

        spec = raw_spec(Airflow, proj)
        spec.parse()
        assert "standalone" in spec._contents["command"]
        assert "webserver" in spec._contents["command"]


class TestKedro:
    FILES = {
        "pyproject.toml": """\
            [tool.kedro]
            package_name = "my_project"
            project_name = "My Project"
            kedro_init_version = "0.19.0"
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Kedro

        assert raw_spec(Kedro, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Kedro

        assert not raw_spec(Kedro, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Kedro

        spec = raw_spec(Kedro, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["package_name"] == "my_project"

    def test_parse_default_run_command(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.dataworkflows import Kedro

        spec = raw_spec(Kedro, proj)
        spec.parse()
        assert "run" in spec._contents["command"]
        assert "run" in spec._artifacts

    def test_parse_pipeline_discovery(self, tmpdir):
        # Create pipeline directories under src/<package>/pipelines/
        files = dict(self.FILES)
        files["src/my_project/pipelines/ingestion/__init__.py"] = ""
        files["src/my_project/pipelines/processing/__init__.py"] = ""
        proj = make_proj(tmpdir, files)
        from projspec.proj.dataworkflows import Kedro

        spec = raw_spec(Kedro, proj)
        spec.parse()
        assert "ingestion" in spec._contents.get("pipeline_stage", {})
        assert "processing" in spec._contents.get("pipeline_stage", {})


class TestDagster:
    FILES_PYPROJECT = {
        "pyproject.toml": """\
            [tool.dagster]
            module_name = "my_assets"
            """,
    }

    FILES_YAML = {
        "dagster.yaml": "telemetry:\n  enabled: false\n",
    }

    def test_match_pyproject(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PYPROJECT)
        from projspec.proj.dataworkflows import Dagster

        assert raw_spec(Dagster, proj).match()

    def test_match_dagster_yaml(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_YAML)
        from projspec.proj.dataworkflows import Dagster

        assert raw_spec(Dagster, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.dataworkflows import Dagster

        assert not raw_spec(Dagster, proj).match()

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PYPROJECT)
        from projspec.proj.dataworkflows import Dagster

        spec = raw_spec(Dagster, proj)
        spec.parse()
        assert "dev" in spec._artifacts
        assert "materialize" in spec._artifacts
        from projspec.artifact.process import Server

        assert isinstance(spec._artifacts["dev"], Server)


# ---------------------------------------------------------------------------
# Documentation specs
# ---------------------------------------------------------------------------


class TestMkDocs:
    FILES = {
        "mkdocs.yml": """\
            site_name: My Project Docs
            site_description: Documentation for my project
            site_author: Alice
            docs_dir: docs
            site_dir: site
            nav:
              - Home: index.md
            theme:
              name: material
            """,
        "docs/index.md": "# Welcome\n",
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.documentation import MkDocs

        assert raw_spec(MkDocs, proj).match()

    def test_match_yaml_extension(self, tmpdir):
        proj = make_proj(tmpdir, {"mkdocs.yaml": "site_name: X\n"})
        from projspec.proj.documentation import MkDocs

        assert raw_spec(MkDocs, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.documentation import MkDocs

        assert not raw_spec(MkDocs, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.documentation import MkDocs

        spec = raw_spec(MkDocs, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["site_name"] == "My Project Docs"
        assert meta["site_author"] == "Alice"

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.documentation import MkDocs

        spec = raw_spec(MkDocs, proj)
        spec.parse()
        assert "docs" in spec._artifacts
        assert "serve" in spec._artifacts
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server

        assert isinstance(spec._artifacts["docs"], StaticSite)
        assert isinstance(spec._artifacts["serve"], Server)

    def test_parse_output_path(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.documentation import MkDocs

        spec = raw_spec(MkDocs, proj)
        spec.parse()
        assert "site" in spec._artifacts["docs"].fn

    def test_parse_custom_site_dir(self, tmpdir):
        proj = make_proj(tmpdir, {"mkdocs.yml": "site_name: X\nsite_dir: public\n"})
        from projspec.proj.documentation import MkDocs

        spec = raw_spec(MkDocs, proj)
        spec.parse()
        assert "public" in spec._artifacts["docs"].fn


class TestSphinx:
    FILES_ROOT = {
        "conf.py": """\
            project = "MyLib"
            author = "Bob"
            release = "1.2.3"
            extensions = []
            html_theme = "alabaster"
            """,
        "index.rst": ".. toctree::\n   intro\n",
    }

    FILES_DOCS_DIR = {
        "docs/conf.py": """\
            project = "MyLib"
            author = "Carol"
            release = "0.1"
            extensions = []
            html_theme = "furo"
            """,
        "docs/index.rst": "Content\n",
    }

    def test_match_root_conf(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_ROOT)
        from projspec.proj.documentation import Sphinx

        assert raw_spec(Sphinx, proj).match()

    def test_match_docs_conf(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_DOCS_DIR)
        from projspec.proj.documentation import Sphinx

        assert raw_spec(Sphinx, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.documentation import Sphinx

        assert not raw_spec(Sphinx, proj).match()

    def test_parse_metadata_root(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_ROOT)
        from projspec.proj.documentation import Sphinx

        spec = raw_spec(Sphinx, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["project"] == "MyLib"
        assert meta["author"] == "Bob"
        assert meta["release"] == "1.2.3"

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_ROOT)
        from projspec.proj.documentation import Sphinx

        spec = raw_spec(Sphinx, proj)
        spec.parse()
        assert "docs" in spec._artifacts
        assert "autobuild" in spec._artifacts
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server

        assert isinstance(spec._artifacts["docs"], StaticSite)
        assert isinstance(spec._artifacts["autobuild"], Server)

    def test_parse_docs_dir_layout(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_DOCS_DIR)
        from projspec.proj.documentation import Sphinx

        spec = raw_spec(Sphinx, proj)
        spec.parse()
        assert "docs" in spec._artifacts["docs"].fn


# ---------------------------------------------------------------------------
# Infrastructure specs
# ---------------------------------------------------------------------------


class TestDockerCompose:
    FILES = {
        "docker-compose.yml": """\
            name: myapp
            services:
              web:
                image: nginx:latest
                ports:
                  - "8080:80"
              db:
                image: postgres:15
                environment:
                  POSTGRES_PASSWORD: secret
              cache:
                image: redis:7
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import DockerCompose

        assert raw_spec(DockerCompose, proj).match()

    def test_match_compose_yaml(self, tmpdir):
        proj = make_proj(
            tmpdir, {"compose.yaml": "services:\n  app:\n    image: alpine\n"}
        )
        from projspec.proj.infra import DockerCompose

        assert raw_spec(DockerCompose, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import DockerCompose

        assert not raw_spec(DockerCompose, proj).match()

    def test_parse_services_as_dependencies(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import DockerCompose

        spec = raw_spec(DockerCompose, proj)
        spec.parse()
        deps = spec._contents["service_dependency"]
        assert "web" in deps
        assert "db" in deps
        assert "cache" in deps

    def test_parse_service_details(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import DockerCompose

        spec = raw_spec(DockerCompose, proj)
        spec.parse()
        db = spec._contents["service_dependency"]["db"]
        assert db.image == "postgres:15"
        assert db.service_type == "postgres"
        assert db.version == "15"

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import DockerCompose

        spec = raw_spec(DockerCompose, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["name"] == "myapp"
        assert "web" in meta["services"]

    def test_parse_stack_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import DockerCompose

        spec = raw_spec(DockerCompose, proj)
        spec.parse()
        from projspec.artifact.infra import ComposeStack

        assert isinstance(spec._artifacts["stack"], ComposeStack)
        assert "docker-compose.yml" in spec._artifacts["stack"].compose_file


class TestTerraform:
    FILES = {
        "main.tf": """\
            terraform {
              required_version = ">= 1.5"
              required_providers {
                aws = {
                  source  = "hashicorp/aws"
                  version = "~> 5.0"
                }
              }
            }

            resource "aws_s3_bucket" "data" {
              bucket = "my-data-bucket"
            }

            resource "aws_lambda_function" "handler" {
              function_name = "my-handler"
              role          = "arn:aws:iam::123:role/role"
              handler       = "index.handler"
              runtime       = "python3.11"
            }
            """,
        "variables.tf": 'variable "region" {\n  default = "us-east-1"\n}\n',
        "outputs.tf": "",
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Terraform

        assert raw_spec(Terraform, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Terraform

        assert not raw_spec(Terraform, proj).match()

    def test_parse_resource_types(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Terraform

        spec = raw_spec(Terraform, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert "aws_s3_bucket" in meta["resource_types"]
        assert "aws_lambda_function" in meta["resource_types"]

    def test_parse_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Terraform

        spec = raw_spec(Terraform, proj)
        spec.parse()
        for cmd in ("init", "validate", "apply", "destroy"):
            assert cmd in spec._contents["command"]
            assert cmd in spec._artifacts

    def test_parse_plan_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Terraform

        spec = raw_spec(Terraform, proj)
        spec.parse()
        from projspec.artifact.infra import TerraformPlan

        assert isinstance(spec._artifacts["plan"], TerraformPlan)
        assert "plan.tfplan" in spec._artifacts["plan"].fn


class TestAnsible:
    FILES_PLAYBOOK = {
        "playbook.yml": """\
            ---
            - name: Configure webservers
              hosts: webservers
              tasks:
                - name: Install nginx
                  apt:
                    name: nginx
                    state: present
            """,
        "inventory": "webserver1 ansible_host=192.168.1.1\n",
    }

    FILES_ROLES = {
        "site.yml": "---\n- hosts: all\n  roles:\n    - common\n",
        "roles/common/tasks/main.yml": "---\n- name: update\n  apt: update_cache=yes\n",
    }

    def test_match_playbook(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PLAYBOOK)
        from projspec.proj.infra import Ansible

        assert raw_spec(Ansible, proj).match()

    def test_match_ansible_cfg(self, tmpdir):
        proj = make_proj(tmpdir, {"ansible.cfg": "[defaults]\ninventory = inventory\n"})
        from projspec.proj.infra import Ansible

        assert raw_spec(Ansible, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Ansible

        assert not raw_spec(Ansible, proj).match()

    def test_parse_playbook_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_PLAYBOOK)
        from projspec.proj.infra import Ansible

        spec = raw_spec(Ansible, proj)
        spec.parse()
        assert "playbook" in spec._contents["command"]
        assert spec._contents["command"]["playbook"].cmd == [
            "ansible-playbook",
            "playbook.yml",
        ]

    def test_parse_site_yml(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_ROLES)
        from projspec.proj.infra import Ansible

        spec = raw_spec(Ansible, proj)
        spec.parse()
        assert "site" in spec._contents["command"]


class TestPulumi:
    FILES = {
        "Pulumi.yaml": """\
            name: my-infra
            runtime: python
            description: Cloud infrastructure for my-infra
            """,
    }

    FILES_DICT_RUNTIME = {
        "Pulumi.yaml": """\
            name: my-infra
            runtime:
              name: python
              options:
                virtualenv: venv
            description: Uses dict runtime
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Pulumi

        assert raw_spec(Pulumi, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Pulumi

        assert not raw_spec(Pulumi, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Pulumi

        spec = raw_spec(Pulumi, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["name"] == "my-infra"
        assert meta["runtime"] == "python"

    def test_parse_metadata_dict_runtime(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES_DICT_RUNTIME)
        from projspec.proj.infra import Pulumi

        spec = raw_spec(Pulumi, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["runtime"] == "python"

    def test_parse_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Pulumi

        spec = raw_spec(Pulumi, proj)
        spec.parse()
        from projspec.artifact.deployment import Deployment

        assert isinstance(spec._artifacts["deploy"], Deployment)
        assert "preview" in spec._artifacts

    def test_parse_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Pulumi

        spec = raw_spec(Pulumi, proj)
        spec.parse()
        assert "up" in spec._contents["command"]
        assert "destroy" in spec._contents["command"]
        assert spec._contents["command"]["up"].cmd == ["pulumi", "up", "--yes"]


class TestCDK:
    FILES = {
        "cdk.json": json.dumps(
            {
                "app": "npx ts-node --prefer-ts-exts bin/app.ts",
                "context": {"@aws-cdk/core:enableStackNameDuplicates": True},
            }
        ),
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import CDK

        assert raw_spec(CDK, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import CDK

        assert not raw_spec(CDK, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import CDK

        spec = raw_spec(CDK, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert "ts-node" in meta["app"]

    def test_parse_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import CDK

        spec = raw_spec(CDK, proj)
        spec.parse()
        for cmd in ("synth", "deploy", "destroy", "diff"):
            assert cmd in spec._contents["command"]

    def test_parse_deploy_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import CDK

        spec = raw_spec(CDK, proj)
        spec.parse()
        from projspec.artifact.deployment import Deployment

        assert isinstance(spec._artifacts["deploy"], Deployment)


class TestEarthfile:
    FILES = {
        "Earthfile": """\
            VERSION 0.8

            build:
                FROM golang:1.21
                RUN go build ./...

            test:
                FROM +build
                RUN go test ./...

            docker:
                FROM alpine:latest
                COPY +build/app /app
                ENTRYPOINT ["/app"]
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Earthfile

        assert raw_spec(Earthfile, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Earthfile

        assert not raw_spec(Earthfile, proj).match()

    def test_parse_targets(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Earthfile

        spec = raw_spec(Earthfile, proj)
        spec.parse()
        assert "build" in spec._contents["command"]
        assert "test" in spec._contents["command"]
        assert "docker" in spec._contents["command"]
        assert spec._contents["command"]["build"].cmd == ["earthly", "+build"]

    def test_parse_uppercase_directives_filtered(self, tmpdir):
        # VERSION, FROM, RUN etc. should not appear as targets
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Earthfile

        spec = raw_spec(Earthfile, proj)
        spec.parse()
        for key in spec._contents.get("command", {}):
            assert (
                key == key.lower() or not key.isupper()
            ), f"All-caps directive '{key}' should be filtered out"


class TestNixpacks:
    FILES = {
        "nixpacks.toml": """\
            [phases.setup]
            nixPkgs = ['python311', 'poetry']

            [phases.install]
            cmds = ['poetry install --no-dev']

            [start]
            cmd = 'uvicorn app:app --host 0.0.0.0'
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Nixpacks

        assert raw_spec(Nixpacks, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Nixpacks

        assert not raw_spec(Nixpacks, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Nixpacks

        spec = raw_spec(Nixpacks, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert "setup" in meta["phases"]
        assert "install" in meta["phases"]
        assert "uvicorn" in meta["start_cmd"]

    def test_parse_docker_image_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Nixpacks

        spec = raw_spec(Nixpacks, proj)
        spec.parse()
        from projspec.artifact.process import Process

        assert isinstance(spec._artifacts["build"], Process)
        assert "nixpacks" in spec._artifacts["build"].cmd[0]


class TestVagrant:
    FILES = {
        "Vagrantfile": """\
            Vagrant.configure("2") do |config|
              config.vm.box = "ubuntu/jammy64"
              config.vm.hostname = "dev-server"
              config.vm.provider "virtualbox" do |vb|
                vb.memory = "2048"
              end
            end
            """,
    }

    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Vagrant

        assert raw_spec(Vagrant, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        from projspec.proj.infra import Vagrant

        assert not raw_spec(Vagrant, proj).match()

    def test_parse_metadata(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Vagrant

        spec = raw_spec(Vagrant, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["box"] == "ubuntu/jammy64"
        assert meta["hostname"] == "dev-server"

    def test_parse_commands(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Vagrant

        spec = raw_spec(Vagrant, proj)
        spec.parse()
        for cmd in ("up", "halt", "destroy", "ssh"):
            assert cmd in spec._contents["command"]
        assert spec._contents["command"]["up"].cmd == ["vagrant", "up"]

    def test_parse_vm_artifact(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        from projspec.proj.infra import Vagrant

        spec = raw_spec(Vagrant, proj)
        spec.parse()
        from projspec.artifact.process import Server

        assert isinstance(spec._artifacts["vm"], Server)


# ---------------------------------------------------------------------------
# Web framework specs (scan-based, no _create)
# ---------------------------------------------------------------------------


class TestGradio:
    GRADIO_APP = """\
        import gradio as gr

        def predict(text):
            return text.upper()

        demo = gr.Interface(fn=predict, inputs="text", outputs="text")

        if __name__ == "__main__":
            demo.launch()
        """

    GRADIO_BLOCKS = """\
        import gradio as gr

        with gr.Blocks() as demo:
            gr.Markdown("Hello!")

        demo.launch()
        """

    def test_match_positive(self, tmpdir):
        write_files(tmpdir, {"app.py": self.GRADIO_APP})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        assert raw_spec(Gradio, proj).match()

    def test_match_negative(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        assert not raw_spec(Gradio, proj).match()

    def test_parse_interface(self, tmpdir):
        write_files(tmpdir, {"app.py": self.GRADIO_APP})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        spec = raw_spec(Gradio, proj)
        spec.parse()
        assert "server" in spec._artifacts
        assert "app" in spec._artifacts["server"]

    def test_parse_blocks(self, tmpdir):
        write_files(tmpdir, {"demo.py": self.GRADIO_BLOCKS})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        spec = raw_spec(Gradio, proj)
        spec.parse()
        assert "demo" in spec._artifacts["server"]

    def test_parse_command_uses_python(self, tmpdir):
        write_files(tmpdir, {"app.py": self.GRADIO_APP})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        spec = raw_spec(Gradio, proj)
        spec.parse()
        cmd = spec._artifacts["server"]["app"].cmd
        assert cmd[0] == "python"

    def test_parse_non_gradio_ignored(self, tmpdir):
        write_files(tmpdir, {"app.py": "import flask\napp = Flask(__name__)\n"})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Gradio

        spec = raw_spec(Gradio, proj)
        from projspec.proj.base import ParseFailed

        with pytest.raises(ParseFailed):
            spec.parse()


class TestShiny:
    SHINY_APP = """\
        from shiny import App, render, ui

        app_ui = ui.page_fluid(
            ui.input_text("name", "Name:"),
            ui.output_text_verbatim("greeting"),
        )

        def server(input, output, session):
            @render.text
            def greeting():
                return f"Hello, {input.name()}!"

        app = App(app_ui, server)
        """

    def test_match_positive(self, tmpdir):
        write_files(tmpdir, {"app.py": self.SHINY_APP})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Shiny

        assert raw_spec(Shiny, proj).match()

    def test_match_negative(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Shiny

        assert not raw_spec(Shiny, proj).match()

    def test_parse_server(self, tmpdir):
        write_files(tmpdir, {"app.py": self.SHINY_APP})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Shiny

        spec = raw_spec(Shiny, proj)
        spec.parse()
        assert "server" in spec._artifacts
        assert "app" in spec._artifacts["server"]
        cmd = spec._artifacts["server"]["app"].cmd
        assert cmd[0] == "shiny"
        assert "run" in cmd

    def test_parse_non_shiny_ignored(self, tmpdir):
        write_files(tmpdir, {"app.py": "import streamlit as st\nst.write('hello')\n"})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.webapp import Shiny

        spec = raw_spec(Shiny, proj)
        from projspec.proj.base import ParseFailed

        with pytest.raises(ParseFailed):
            spec.parse()


# ---------------------------------------------------------------------------
# New content types
# ---------------------------------------------------------------------------


class TestCIWorkflow:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.content.cicd import CIWorkflow

        wf = CIWorkflow(
            proj=proj,
            name="My Workflow",
            triggers=["push", "pull_request"],
            jobs=["build", "test"],
            provider="github",
        )
        assert wf.name == "My Workflow"
        assert "push" in wf.triggers
        assert "build" in wf.jobs
        assert wf.provider == "github"

    def test_to_dict(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.content.cicd import CIWorkflow

        wf = CIWorkflow(
            proj=proj,
            name="CI",
            triggers=["push"],
            jobs=["test"],
            provider="github",
        )
        d = wf.to_dict(compact=True)
        assert d["name"] == "CI"
        assert d["provider"] == "github"

    def test_registered(self):
        from projspec.content.base import registry

        assert "c_i_workflow" in registry


class TestPipelineStage:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.content.cicd import PipelineStage

        stage = PipelineStage(
            proj=proj,
            name="process",
            cmd=["snakemake", "process"],
            depends_on=["download"],
        )
        assert stage.name == "process"
        assert stage.cmd == ["snakemake", "process"]
        assert "download" in stage.depends_on

    def test_registered(self):
        from projspec.content.base import registry

        assert "pipeline_stage" in registry


class TestServiceDependency:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.content.cicd import ServiceDependency

        svc = ServiceDependency(
            proj=proj,
            name="db",
            service_type="postgres",
            version="15",
            image="postgres:15",
        )
        assert svc.name == "db"
        assert svc.service_type == "postgres"
        assert svc.version == "15"

    def test_registered(self):
        from projspec.content.base import registry

        assert "service_dependency" in registry


# ---------------------------------------------------------------------------
# New artifact types
# ---------------------------------------------------------------------------


class TestComposeStack:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.artifact.infra import ComposeStack

        stack = ComposeStack(proj=proj, file="docker-compose.yml")
        assert stack.compose_file == "docker-compose.yml"
        assert "docker" in stack.cmd[0]
        assert "compose" in stack.cmd

    def test_registered(self):
        from projspec.artifact.base import registry

        assert "compose_stack" in registry

    def test_state_unknown_remote(self, tmpdir):
        from projspec.artifact.infra import ComposeStack
        from unittest.mock import MagicMock

        # Simulate a remote (non-LocalFileSystem) project
        proj = projspec.Project.__new__(projspec.Project)
        mock_fs = MagicMock()
        mock_fs.__class__.__name__ = "S3FileSystem"
        # is_local() uses isinstance check against LocalFileSystem
        import fsspec.implementations.local

        mock_fs.__class__ = type("S3FileSystem", (), {})
        proj.fs = mock_fs
        proj.url = "bucket/prefix"
        stack = ComposeStack(proj=proj)
        # Remote project: state should be "" (unknown)
        assert stack.state == ""


class TestStaticSite:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.artifact.infra import StaticSite

        site = StaticSite(
            proj=proj, cmd=["mkdocs", "build"], fn="/path/site/index.html"
        )
        assert site.fn == "/path/site/index.html"
        assert site.cmd == ["mkdocs", "build"]

    def test_registered(self):
        from projspec.artifact.base import registry

        assert "static_site" in registry

    def test_is_done_when_file_exists(self, tmpdir):
        path = str(tmpdir)
        os.makedirs(os.path.join(path, "site"))
        index = os.path.join(path, "site", "index.html")
        open(index, "w").close()
        proj = projspec.Project(path)
        from projspec.artifact.infra import StaticSite

        site = StaticSite(proj=proj, cmd=["mkdocs", "build"], fn=index)
        assert site._is_done()

    def test_is_clean_when_file_absent(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.artifact.infra import StaticSite

        site = StaticSite(
            proj=proj,
            cmd=["mkdocs", "build"],
            fn=str(tmpdir.join("site/index.html")),
        )
        assert site._is_clean()


class TestTerraformPlan:
    def test_fields(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.artifact.infra import TerraformPlan

        plan = TerraformPlan(proj=proj)
        assert "plan.tfplan" in plan.fn
        assert plan.cmd == ["terraform", "plan", "-out", "plan.tfplan"]

    def test_custom_plan_file(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.artifact.infra import TerraformPlan

        plan = TerraformPlan(proj=proj, plan_file="infra.tfplan")
        assert "infra.tfplan" in plan.fn
        assert "infra.tfplan" in plan.cmd

    def test_registered(self):
        from projspec.artifact.base import registry

        assert "terraform_plan" in registry


# ---------------------------------------------------------------------------
# Metaflow
# ---------------------------------------------------------------------------

HELLO_FLOW = """\
from metaflow import FlowSpec, step


class HelloFlow(FlowSpec):
    @step
    def start(self):
        print("Hello!")
        self.next(self.end)

    @step
    def end(self):
        print("Done.")


if __name__ == "__main__":
    HelloFlow()
"""

TRAIN_FLOW = """\
from metaflow import FlowSpec, step, project, schedule, Parameter


@project(name="my_ml_project")
@schedule(daily=True)
class TrainFlow(FlowSpec):
    learning_rate = Parameter("lr", default=0.01)

    @step
    def start(self):
        self.next(self.train)

    @step
    def train(self):
        print(f"Training with lr={self.learning_rate}")
        self.next(self.end)

    @step
    def end(self):
        print("Training complete")


if __name__ == "__main__":
    TrainFlow()
"""

NOT_METAFLOW = """\
import pandas as pd

def process():
    return pd.DataFrame({"a": [1, 2, 3]})
"""


class TestMetaflow:
    def test_match_positive(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        assert raw_spec(Metaflow, proj).match()

    def test_match_negative_no_py(self, tmpdir):
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        assert not raw_spec(Metaflow, proj).match()

    def test_match_negative_non_metaflow_py(self, tmpdir):
        write_files(tmpdir, {"script.py": NOT_METAFLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        assert not raw_spec(Metaflow, proj).match()

    def test_match_requires_both_import_and_flowspec(self, tmpdir):
        # import present but no FlowSpec subclass
        write_files(
            tmpdir,
            {"util.py": "from metaflow import Parameter\nx = Parameter('n')\n"},
        )
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        assert not raw_spec(Metaflow, proj).match()

    def test_parse_run_command(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        assert "flow" in spec._contents["command"]
        assert spec._contents["command"]["flow"].cmd == [
            "python",
            "flow.py",
            "run",
        ]

    def test_parse_process_artifact(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        assert "flow" in spec._artifacts["process"]
        assert spec._artifacts["process"]["flow"].cmd == [
            "python",
            "flow.py",
            "run",
        ]

    def test_parse_step_names_as_pipeline_stages(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        stages = spec._contents.get("pipeline_stage", {})
        assert "flow.start" in stages
        assert "flow.end" in stages

    def test_parse_project_name_from_decorator(self, tmpdir):
        write_files(tmpdir, {"train.py": TRAIN_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        meta = spec._contents["descriptive_metadata"].meta
        assert meta["project"] == "my_ml_project"

    def test_parse_deployment_artifacts_when_scheduled(self, tmpdir):
        write_files(tmpdir, {"train.py": TRAIN_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        procs = spec._artifacts["process"]
        assert "train.argo_create" in procs
        assert "train.step_functions_create" in procs
        assert procs["train.argo_create"].cmd == [
            "python",
            "train.py",
            "argo-workflows",
            "create",
        ]
        assert procs["train.step_functions_create"].cmd == [
            "python",
            "train.py",
            "step-functions",
            "create",
        ]

    def test_parse_no_deployment_artifacts_without_schedule(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        procs = spec._artifacts["process"]
        assert not any("argo" in k or "step_functions" in k for k in procs)

    def test_parse_multiple_flows(self, tmpdir):
        write_files(tmpdir, {"flow.py": HELLO_FLOW, "train.py": TRAIN_FLOW})
        proj = projspec.Project(str(tmpdir))
        from projspec.proj.dataworkflows import Metaflow

        spec = raw_spec(Metaflow, proj)
        spec.parse()
        assert "flow" in spec._contents["command"]
        assert "train" in spec._contents["command"]

    def test_create_writes_flow_file(self, tmpdir):
        path = str(tmpdir)
        from projspec.proj.dataworkflows import Metaflow

        Metaflow._create(path)
        flow_file = os.path.join(path, "flow.py")
        assert os.path.exists(flow_file)
        content = open(flow_file).read()
        assert "FlowSpec" in content
        assert "@step" in content
        assert "def start" in content
        assert "def end" in content
        assert "if __name__" in content

    def test_create_flow_class_name_derived_from_dir(self, tmpdir):
        path = str(tmpdir.mkdir("my_pipeline"))
        from projspec.proj.dataworkflows import Metaflow

        Metaflow._create(path)
        content = open(os.path.join(path, "flow.py")).read()
        assert "MyPipelineFlow" in content

    def test_roundtrip_create_and_detect(self, tmpdir):
        """create() produces files that match() and parse() accept."""
        path = str(tmpdir)
        proj = projspec.Project(path)
        proj.create("Metaflow")
        # Re-scan so scanned_files picks up the new flow.py
        proj2 = projspec.Project(path)
        assert "metaflow" in proj2
