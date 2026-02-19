from pathlib import Path
import os.path
import toml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict, PickleableTomlDecoder, make_and_copy


class PyScript(ProjectSpec):
    """PyScript is an open source platform for Python in the browser.

    This spec is the canonical way to provide configuration, and included in new template
    apps on pyscript.com.
    """

    spec_doc = "https://docs.pyscript.net/2023.11.2/user-guide/configuration/"

    def match(self) -> bool:
        # actually, config can be specified by a local path in the repo, but this is rare;
        # also you can just declare things to install as you go, which we won't be able to
        # guess.
        return not {"pyscript.toml", "pyscript.json"}.isdisjoint(self.proj.basenames)

    def parse(self) -> None:
        from projspec.content.environment import Environment, Precision, Stack
        from projspec.artifact.process import Server

        try:
            with self.proj.fs.open(f"{self.proj.url}/pyscript.toml", "rt") as f:
                meta = toml.load(f, decoder=PickleableTomlDecoder())
        except FileNotFoundError:
            with self.proj.fs.open(f"{self.proj.url}/pyscript.json", "rt") as f:
                meta = toml.load(f, decoder=PickleableTomlDecoder())
        cont = AttrDict()
        if "packages" in meta:
            cont["environment"] = AttrDict(
                default=Environment(
                    proj=self.proj,
                    artifacts=set(),
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                    packages=meta["packages"],
                )
            )
        self._contents = cont

        # perhaps a local deployment can be a reasonable artifact
        # https://github.com/pyscript/pyscript-cli
        # TODO: the server app is very small, could launch with uvx or such directly
        #  or embed.
        self._artifacts = AttrDict(
            {"server": Server(proj=self.proj, cmd=["pyscript", "run"])}
        )

    @staticmethod
    def _create(path: str) -> None:
        create_project(Path(path))


TEMPLATE_PYTHON_CODE = """# Replace the code below with your own
print("Hello, world!")
"""
TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <title>{{ title }}</title>

    <!-- Recommended meta tags -->
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">

    <link rel="stylesheet" href="https://pyscript.net/releases/2026.2.1/core.css">
    <script type="module" src="https://pyscript.net/releases/2026.2.1/core.js"></script>
  </head>
  <body>
    <script type="py" src="./main.py" config="./pyscript.toml" terminal></script>
  </body>
</html>"""


def create_project(
    app_dir: Path,
) -> None:
    # modified from
    # https://github.com/pyscript/pyscript-cli/blob/main/src/pyscript/_generator.py
    app_name = "projspec-app"

    context = {
        "name": app_name,
        "description": "Pyscript template by projspec",
        "type": "app",
        "author_name": "temp",
        "author_email": "temp",
        "version": "latest",
        "packages": [],
    }

    os.makedirs(str(app_dir), exist_ok=True)
    manifest_file = app_dir / "pyscript.toml"
    with manifest_file.open("w") as fp:
        toml.dump(context, fp)
    output_path = app_dir / "index.html"
    python_filepath = app_dir / "main.py"

    with python_filepath.open("w", encoding="utf-8") as fp:
        fp.write(TEMPLATE_PYTHON_CODE)

    with output_path.open("w") as fp:
        fp.write(TEMPLATE_HTML)
