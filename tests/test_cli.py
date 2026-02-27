import os
import projspec
from projspec.__main__ import main


def test1(capsys):
    main([], standalone_mode=False)
    assert "Project" in capsys.readouterr().out

    main(["--json-out"], standalone_mode=False)
    assert capsys.readouterr().out.startswith("{")


def test_help(capsys):
    main(["--help"], standalone_mode=False)
    assert "Options:" in capsys.readouterr().out


def test_version(capsys):
    main(["--version"], standalone_mode=False)
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
    main([path, "--make", "process"], standalone_mode=False)
    main([path, "--make", "python_code.process"], standalone_mode=False)
    main([path, "--make", "python_code.process.main"], standalone_mode=False)
    time.sleep(0.7)  # wait for the files to arrive
    assert len(os.listdir(path)) == 5
