import os

import pytest

import projspec
from projspec.__main__ import main


def test1(capsys):
    main(["scan"], standalone_mode=False)
    assert "Project" in capsys.readouterr().out

    main(["scan", "--json-out"], standalone_mode=False)
    assert capsys.readouterr().out.startswith("{")


def test_help(capsys):
    main(["--help"], standalone_mode=False)
    assert "Options:" in capsys.readouterr().out


def test_version(capsys):
    main(["version"], standalone_mode=False)
    assert projspec.__version__ in capsys.readouterr().out


def test_make(tmpdir):
    import fsspec
    import time

    fsspec.utils.setup_logging(logger_name="projspec", level="INFO")
    path = str(tmpdir)
    open(path + "/__init__.py", "w").close()
    with open(path + "/__main__.py", "w") as f:
        f.write(
            """
import time

open(str(time.time()), "w").close()
"""
        )
    main(["make", "process", path], standalone_mode=False)
    main(["make", "python_code.process", path], standalone_mode=False)
    main(["make", "python_code.process.main", path], standalone_mode=False)
    time.sleep(1.7)  # wait for the files to arrive; perhaps --wait should be a thing
    assert len(os.listdir(path)) == 5


@pytest.fixture
def temp_conf_dir(tmpdir):
    os.environ["PROJSPEC_CONFIG_DIR"] = str(tmpdir)
    with projspec.config.temp_conf():
        projspec.config.load_conf()
        yield str(tmpdir)


def test_config(temp_conf_dir, capsys):
    main(["config", "get", "scan_max_files"], standalone_mode=False)
    assert "100" in capsys.readouterr().out
    main(["config", "show"], standalone_mode=False)
    assert "{}" in capsys.readouterr().out
    main(["config", "set", "scan_max_files", "200"], standalone_mode=False)
    assert os.path.exists(f"{temp_conf_dir}/projspec.json")
    main(["config", "get", "scan_max_files"], standalone_mode=False)
    assert "200" in capsys.readouterr().out
    main(["config", "unset", "scan_max_files"], standalone_mode=False)
    main(["config", "get", "scan_max_files"], standalone_mode=False)
    assert "100" in capsys.readouterr().out


def test_library(temp_conf_dir, capsys):
    projspec.config.set_conf("library_path", f"{temp_conf_dir}/library.json")
    main(["library", "list"], standalone_mode=False)
    assert capsys.readouterr().out == ""
    main(["scan", "--library"], standalone_mode=False)
    capsys.readouterr()
    main(["library", "list"], standalone_mode=False)
    out = capsys.readouterr().out
    assert "PythonLibrary" in out
    path = out.split()[0]
    main(["library", "delete", path], standalone_mode=False)
    main(["library", "list"], standalone_mode=False)
    assert capsys.readouterr().out == ""


def test_create_cant(tmpdir, capsys):
    try:
        main(["create", "project_extra", str(tmpdir)], standalone_mode=False)
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "does not support creation" in out
    assert "python_code" in out
