import os
import tempfile

import projspec
from projspec.proj.webapp import Marimo


# Sample marimo notebook content
MARIMO_NOTEBOOK = b"""import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def _():
    import pandas as pd
    return (pd,)


@app.cell
def _(pd):
    df = pd.DataFrame({"a": [1, 2, 3]})
    df
    return (df,)


if __name__ == "__main__":
    app.run()
"""

MARIMO_NOTEBOOK_ALT = b"""from marimo import App

app = App()


@app.cell
def _():
    print("Hello, marimo!")
    return


if __name__ == "__main__":
    app.run()
"""

NOT_MARIMO = b"""import pandas as pd

def main():
    df = pd.DataFrame({"a": [1, 2, 3]})
    print(df)

if __name__ == "__main__":
    main()
"""


def test_marimo_single_notebook():
    """Test detection of a single marimo notebook"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a marimo notebook
        notebook_path = os.path.join(tmpdir, "notebook.py")
        with open(notebook_path, "wb") as f:
            f.write(MARIMO_NOTEBOOK)

        proj = projspec.Project(tmpdir)
        assert "marimo" in proj.specs
        spec = proj.specs["marimo"]

        # Should have server artifact
        assert "server" in spec.artifacts
        assert "notebook" in spec.artifacts["server"]

        # Check the command
        assert spec.artifacts["server"]["notebook"].cmd == [
            "marimo",
            "run",
            "notebook.py",
        ]


def test_marimo_multiple_notebooks():
    """Test detection of multiple marimo notebooks"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create multiple marimo notebooks
        for name, content in [
            ("app1.py", MARIMO_NOTEBOOK),
            ("app2.py", MARIMO_NOTEBOOK_ALT),
        ]:
            path = os.path.join(tmpdir, name)
            with open(path, "wb") as f:
                f.write(content)

        proj = projspec.Project(tmpdir)
        assert "marimo" in proj.specs
        spec = proj.specs["marimo"]

        # Should have nested artifacts for each notebook
        assert isinstance(spec.artifacts["server"], dict)
        assert "app1" in spec.artifacts["server"]
        assert "app2" in spec.artifacts["server"]


def test_marimo_not_detected_for_regular_python():
    """Test that regular Python files are not detected as marimo"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a regular Python file
        path = os.path.join(tmpdir, "script.py")
        with open(path, "wb") as f:
            f.write(NOT_MARIMO)

        proj = projspec.Project(tmpdir)
        assert "marimo" not in proj.specs


def test_marimo_match_requires_both_import_and_app():
    """Test that both import and App() are required for detection"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file with just the import but no App
        path = os.path.join(tmpdir, "partial.py")
        with open(path, "wb") as f:
            f.write(b"import marimo\n\nprint('hello')\n")

        proj = projspec.Project(tmpdir)
        # match() returns True (has import), but parse() should fail
        # because there's no App pattern
        assert "marimo" not in proj.specs


def test_marimo_spec_doc():
    """Test that spec_doc is set correctly"""
    assert Marimo.spec_doc == "https://docs.marimo.io/"
