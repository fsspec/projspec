"""Tests for the :class:`AnacondaProject` spec (legacy ``anaconda-project.yml``).

Fixtures are hand-written but modelled on the real sample projects at
https://github.com/anaconda/workbench-sample-projects and the examples in
https://github.com/anaconda/anaconda-project/tree/master/examples .
"""
import os
import textwrap

import projspec
from projspec.proj.anaconda_project import AnacondaProject


def write_files(tmpdir, files: dict) -> str:
    path = str(tmpdir)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(textwrap.dedent(content))
    return path


def make_proj(tmpdir, files: dict):
    return projspec.Project(write_files(tmpdir, files))


def raw_spec(cls, proj):
    inst = cls.__new__(cls)
    inst.proj = proj
    inst._contents = None
    inst._artifacts = None
    return inst


HELLO_ANACONDA = {
    "anaconda-project.yml": """\
        name: Hello Anaconda Enterprise
        description: A simple hello-world anaconda-project app.
        categories:
          - Python

        commands:
          default:
            unix: python ${PROJECT_DIR}/hello.py
            windows: python %PROJECT_DIR%\\hello.py
            supports_http_options: true
          run:
            unix: python ${PROJECT_DIR}/run.py

        variables:
          INTEGRATION_TEST_ANACONDA:
            default: anaconda
          INTEGRATION_TEST_VERSION:
            default: test

        packages:
          - python=3.7
          - ipykernel
        platforms:
          - linux-64

        env_specs:
          python_37: {}
        """,
}


class TestMatch:
    def test_match_positive(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        assert raw_spec(AnacondaProject, proj).match()

    def test_match_yaml_extension(self, tmpdir):
        files = {"anaconda-project.yaml": HELLO_ANACONDA["anaconda-project.yml"]}
        proj = make_proj(tmpdir, files)
        assert raw_spec(AnacondaProject, proj).match()

    def test_match_negative(self, tmpdir):
        proj = make_proj(tmpdir, {})
        assert not raw_spec(AnacondaProject, proj).match()

    def test_conda_project_yml_does_not_match(self, tmpdir):
        """Sanity check: an unrelated conda-project manifest should not match."""
        proj = make_proj(tmpdir, {"conda-project.yml": "name: x\n"})
        assert not raw_spec(AnacondaProject, proj).match()


class TestBasicParse:
    def test_spec_registered(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        assert "anaconda_project" in proj.specs

    def test_commands(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        cmds = proj.specs["anaconda_project"].contents["command"]
        assert set(cmds) == {"default", "run"}
        assert cmds["default"].cmd == "python ${PROJECT_DIR}/hello.py"
        assert cmds["run"].cmd == "python ${PROJECT_DIR}/run.py"

    def test_env_spec(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert "python_37" in envs
        env = envs["python_37"]
        assert env.stack.name == "CONDA"
        assert env.precision.name == "SPEC"
        assert env.packages == ["python=3.7", "ipykernel"]

    def test_variables(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        vars_content = proj.specs["anaconda_project"].contents["environment_variables"]
        assert vars_content.variables == {
            "INTEGRATION_TEST_ANACONDA": "anaconda",
            "INTEGRATION_TEST_VERSION": "test",
        }

    def test_artifacts(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        arts = proj.specs["anaconda_project"].artifacts
        assert "python_37" in arts["conda_env"]
        assert "python_37" in arts["lock_file"]
        assert set(arts["process"]) == {"default", "run"}

    def test_extras_carry_unmodelled_fields(self, tmpdir):
        proj = make_proj(tmpdir, HELLO_ANACONDA)
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["name"] == "Hello Anaconda Enterprise"
        assert meta["categories"] == ["Python"]
        assert meta["platforms"] == ["linux-64"]
        assert meta["command_supports_http_options"] == {"default": True}


class TestInheritance:
    FILES = {
        "anaconda-project.yml": """\
            name: inh
            channels: [defaults]
            packages:
              - python
            platforms: [linux-64]
            env_specs:
              test_packages:
                packages: [pytest, pytest-cov]
              app_dependencies:
                packages: [bokeh]
              app_test_dependencies:
                inherit_from: [test_packages, app_dependencies]
                packages: [tornado]
            commands:
              test:
                unix: python -m pytest myapp/tests
                env_spec: app_test_dependencies
            """,
    }

    def test_inherited_packages_flattened(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert envs["app_test_dependencies"].packages == [
            "python",
            "pytest",
            "pytest-cov",
            "bokeh",
            "tornado",
        ]

    def test_top_level_channels_propagate(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert envs["test_packages"].channels == ["defaults"]

    def test_command_env_spec_recorded(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["command_env_specs"] == {"test": "app_test_dependencies"}


class TestPipDependencies:
    FILES = {
        "anaconda-project.yml": """\
            name: pipproj
            packages:
              - python
              - pip:
                - requests>=2.28
                - flask==3.0
            platforms: [linux-64]
            env_specs:
              default: {}
            """,
    }

    def test_pip_split_into_separate_environment(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert envs["default"].packages == ["python"]
        assert envs["default"].stack.name == "CONDA"
        assert envs["default.pip"].packages == ["requests>=2.28", "flask==3.0"]
        assert envs["default.pip"].stack.name == "PIP"


class TestCommandKinds:
    FILES = {
        "anaconda-project.yml": """\
            name: kinds
            packages: [python]
            platforms: [linux-64]
            env_specs:
              default: {}
            commands:
              notebook_cmd:
                notebook: analysis.ipynb
              bokeh_cmd:
                bokeh_app: .
              shell_cmd:
                unix: echo hi
              string_cmd: echo direct
            """,
    }

    def test_notebook_translated_to_jupyter(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        cmds = proj.specs["anaconda_project"].contents["command"]
        assert cmds["notebook_cmd"].cmd == "jupyter notebook analysis.ipynb"

    def test_bokeh_app_translated(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        cmds = proj.specs["anaconda_project"].contents["command"]
        assert cmds["bokeh_cmd"].cmd == "bokeh serve ."

    def test_plain_unix_passthrough(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        cmds = proj.specs["anaconda_project"].contents["command"]
        assert cmds["shell_cmd"].cmd == "echo hi"

    def test_bare_string_command(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        cmds = proj.specs["anaconda_project"].contents["command"]
        assert cmds["string_cmd"].cmd == "echo direct"

    def test_original_kind_preserved_in_extras(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["command_kinds"] == {
            "notebook_cmd": {"notebook": "analysis.ipynb"},
            "bokeh_cmd": {"bokeh_app": "."},
        }


class TestLockFile:
    MANIFEST = """\
        name: Stocks Example
        commands:
          default:
            bokeh_app: .
        packages:
          - bokeh=0.12
          - pandas
        env_specs:
          default: {}
        platforms:
          - linux-64
          - osx-64
          - win-64
        """
    LOCK = """\
        locking_enabled: true
        env_specs:
          default:
            locked: true
            platforms: [linux-64, osx-64, win-64]
            packages:
              all:
                - bokeh=0.12.5=py27_0
                - pandas=0.20.1=np112py27_0
              unix:
                - openssl=1.0.2k=2
              win-64:
                - vs2008_runtime=9.00.30729.5054=0
        """

    def test_lock_precision_environment_emitted(self, tmpdir):
        proj = make_proj(
            tmpdir,
            {
                "anaconda-project.yml": self.MANIFEST,
                "anaconda-project-lock.yml": self.LOCK,
            },
        )
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert "default.lock" in envs
        locked = envs["default.lock"]
        assert locked.precision.name == "LOCK"
        assert "bokeh=0.12.5=py27_0" in locked.packages
        assert "openssl=1.0.2k=2" in locked.packages
        assert "vs2008_runtime=9.00.30729.5054=0" in locked.packages

    def test_locking_enabled_carried_in_extras(self, tmpdir):
        proj = make_proj(
            tmpdir,
            {
                "anaconda-project.yml": self.MANIFEST,
                "anaconda-project-lock.yml": self.LOCK,
            },
        )
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["locking_enabled"] is True

    def test_no_lock_file_no_lock_environment(self, tmpdir):
        proj = make_proj(tmpdir, {"anaconda-project.yml": self.MANIFEST})
        envs = proj.specs["anaconda_project"].contents["environment"]
        assert "default.lock" not in envs


class TestDownloadsAndServices:
    FILES = {
        "anaconda-project.yml": """\
            name: downloads
            packages: [python]
            platforms: [linux-64]
            env_specs:
              default: {}
            downloads:
              DATA:
                url: https://example.com/data.parq
                filename: data/x.parq
            services:
              REDIS_URL: redis
            """,
    }

    def test_downloads_carried_verbatim(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["downloads"] == {
            "DATA": {
                "url": "https://example.com/data.parq",
                "filename": "data/x.parq",
            }
        }

    def test_services_carried_verbatim(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        meta = proj.specs["anaconda_project"].contents["descriptive_metadata"].meta
        assert meta["services"] == {"REDIS_URL": "redis"}


class TestVariableForms:
    def test_list_form(self, tmpdir):
        proj = make_proj(
            tmpdir,
            {
                "anaconda-project.yml": """\
                    name: v
                    packages: [python]
                    platforms: [linux-64]
                    env_specs: {default: {}}
                    variables:
                      - FOO
                      - BAR
                    """,
            },
        )
        vars_content = proj.specs["anaconda_project"].contents["environment_variables"]
        assert vars_content.variables == {"FOO": None, "BAR": None}

    def test_dict_form_without_default(self, tmpdir):
        proj = make_proj(
            tmpdir,
            {
                "anaconda-project.yml": """\
                    name: v
                    packages: [python]
                    platforms: [linux-64]
                    env_specs: {default: {}}
                    variables:
                      NEEDED:
                        description: please set me
                    """,
            },
        )
        vars_content = proj.specs["anaconda_project"].contents["environment_variables"]
        assert vars_content.variables == {"NEEDED": None}
