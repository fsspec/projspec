import os
import re

import toml

from projspec.proj import ProjectSpec
from projspec.proj.base import ParseFailed
from projspec.utils import AttrDict, PickleableTomlDecoder


class MDBook(ProjectSpec):
    """mdBook is a command line tool to create books with Markdown.

    mdBook is used by the Rust programming language project, and The Rust Programming Language book
    is an example.
    """

    # to get generated docs output for a rust lib, use `rustdoc`
    # https://doc.rust-lang.org/rustdoc/what-is-rustdoc.html

    spec_doc = "https://rust-lang.github.io/mdBook/format/configuration/index.html"

    def match(self) -> bool:
        return "book.toml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Server
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.get_file("book.toml", text=False) as f:
                cfg = toml.loads(f.read().decode(), decoder=PickleableTomlDecoder())
        except (OSError, toml.TomlDecodeError) as exc:
            raise ParseFailed(f"Could not read book.toml: {exc}") from exc

        book = cfg.get("book", {})

        # ------------------------------------------------------------------ #
        # Contents — descriptive metadata from the [book] table
        # ------------------------------------------------------------------ #
        meta: dict[str, str] = {}
        for key in ("title", "description", "language"):
            if val := book.get(key):
                meta[key] = str(val)
        authors = book.get("authors", [])
        if authors:
            meta["authors"] = ", ".join(authors)

        self._contents = AttrDict(
            descriptive_metadata=DescriptiveMetadata(proj=self.proj, meta=meta)
        )

        # ------------------------------------------------------------------ #
        # Artifacts
        # ------------------------------------------------------------------ #
        # build-dir defaults to "book/" relative to the book root
        build_dir = cfg.get("build", {}).get("build-dir", "book")
        if not build_dir.startswith("/"):
            build_dir = f"{self.proj.url}/{build_dir}"

        arts = AttrDict()
        # mdbook build → produces static HTML in build-dir
        arts["book"] = FileArtifact(
            proj=self.proj,
            cmd=["mdbook", "build"],
            fn=f"{build_dir}/index.html",
        )
        # mdbook serve → live-reloading local server
        arts["server"] = Server(
            proj=self.proj,
            cmd=["mdbook", "serve"],
        )

        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal but valid mdBook project."""
        name = os.path.basename(path)

        # book.toml — required configuration file
        with open(f"{path}/book.toml", "wt") as f:
            f.write(
                f"[book]\n"
                f'title = "{name}"\n'
                f"authors = []\n"
                f'description = ""\n'
                f"\n"
                f"[build]\n"
                f'build-dir = "book"\n'
            )

        # src/SUMMARY.md — required entry point
        os.makedirs(f"{path}/src", exist_ok=True)
        with open(f"{path}/src/SUMMARY.md", "wt") as f:
            f.write(f"# Summary\n\n- [Introduction](./introduction.md)\n")

        # src/introduction.md — first chapter
        with open(f"{path}/src/introduction.md", "wt") as f:
            f.write(f"# Introduction\n\nWelcome to {name}.\n")


class RTD(ProjectSpec):
    """Documentation to be processes by ReadTheDocs

    RTD is commonly used by open-source python projects and others. Documentation is
    typically built automatically from github repos using sphinx or mkdocs.

    General description of the platform: https://docs.readthedocs.com/platform/stable/
    """

    spec_doc = "https://docs.readthedocs.com/platform/stable/config-file/v2.html"

    def match(self) -> bool:
        return any(re.match("[.]?readthedocs.y[a]?ml", _) for _ in self.proj.basenames)

    def parse(self) -> None:
        import yaml

        from projspec.artifact.base import FileArtifact
        from projspec.content.environment import Environment, Precision, Stack

        # Locate and read the config file
        cfg_name = next(
            _ for _ in self.proj.basenames if re.match("[.]?readthedocs.y[a]?ml", _)
        )
        try:
            with self.proj.get_file(cfg_name) as f:
                cfg = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as exc:
            raise ParseFailed(f"Could not read {cfg_name}: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(f"{cfg_name} did not parse to a mapping")

        conts = AttrDict()
        arts = AttrDict()

        # ------------------------------------------------------------------ #
        # Environment — conda env file or pip requirements files
        # ------------------------------------------------------------------ #
        conda_env_path = cfg.get("conda", {}).get("environment")
        if conda_env_path:
            try:
                with self.proj.fs.open(f"{self.proj.url}/{conda_env_path}", "rt") as f:
                    env_data = yaml.safe_load(f)
                conts["environment"] = AttrDict(
                    default=Environment(
                        proj=self.proj,
                        stack=Stack.CONDA,
                        precision=Precision.SPEC,
                        packages=env_data.get("dependencies", []),
                        channels=env_data.get("channels", []),
                    )
                )
            except (OSError, yaml.YAMLError):
                pass
        else:
            # Collect requirements files listed under python.install[*].requirements
            req_packages: list[str] = []
            for install in cfg.get("python", {}).get("install", []):
                req_path = install.get("requirements")
                if not req_path:
                    continue
                try:
                    with self.proj.get_file(req_path, text=False) as f:
                        lines = [
                            ln.strip()
                            for ln in f.read().decode().splitlines()
                            if ln.strip() and not ln.strip().startswith("#")
                        ]
                    req_packages.extend(lines)
                except OSError:
                    pass
            if req_packages:
                # Add python version constraint if declared
                py_ver = cfg.get("build", {}).get("tools", {}).get("python")
                if py_ver:
                    req_packages.append(f"python =={py_ver}.*")
                precision = (
                    Precision.LOCK
                    if all(
                        "==" in p for p in req_packages if not p.startswith("python")
                    )
                    else Precision.SPEC
                )
                conts["environment"] = AttrDict(
                    default=Environment(
                        proj=self.proj,
                        stack=Stack.PIP,
                        precision=precision,
                        packages=req_packages,
                    )
                )

        # ------------------------------------------------------------------ #
        # Artifacts — sphinx or mkdocs build process
        # ------------------------------------------------------------------ #
        if "sphinx" in cfg:
            conf_py = cfg["sphinx"].get("configuration", "docs/conf.py")
            docs_dir = conf_py.rsplit("/", 1)[0] if "/" in conf_py else "."
            arts["docs"] = FileArtifact(
                proj=self.proj,
                cmd=[
                    "sphinx-build",
                    "-b",
                    "html",
                    docs_dir,
                    f"{docs_dir}/_build/html",
                ],
                fn=f"{self.proj.url}/{docs_dir}/_build/html/index.html",
            )
        elif "mkdocs" in cfg:
            arts["docs"] = FileArtifact(
                proj=self.proj,
                cmd=["mkdocs", "build"],
                fn=f"{self.proj.url}/site/index.html",
            )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal RTD project using Sphinx."""
        # .readthedocs.yaml — RTD configuration
        with open(f"{path}/.readthedocs.yaml", "wt") as f:
            f.write(
                "version: 2\n"
                "\n"
                "build:\n"
                "  os: ubuntu-24.04\n"
                "  tools:\n"
                '    python: "3.12"\n'
                "\n"
                "sphinx:\n"
                "  configuration: docs/conf.py\n"
                "\n"
                "python:\n"
                "  install:\n"
                "    - requirements: docs/requirements.txt\n"
            )

        # docs/conf.py — minimal Sphinx configuration
        os.makedirs(f"{path}/docs", exist_ok=True)
        name = os.path.basename(path)
        with open(f"{path}/docs/conf.py", "wt") as f:
            f.write(
                f'project = "{name}"\n'
                f"extensions = []\n"
                f'html_theme = "alabaster"\n'
            )

        # docs/index.rst — root document
        with open(f"{path}/docs/index.rst", "wt") as f:
            f.write(f"{name}\n{'=' * len(name)}\n\n.. toctree::\n   :maxdepth: 2\n")

        # docs/requirements.txt — build dependencies
        with open(f"{path}/docs/requirements.txt", "wt") as f:
            f.write("sphinx\n")
