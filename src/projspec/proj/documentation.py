import os
import re

import toml
import yaml

from projspec.proj import ProjectSpec
from projspec.proj.base import ParseFailed
from projspec.utils import AttrDict, PickleableTomlDecoder


class MDBook(ProjectSpec):
    """mdBook is a command line tool to create books with Markdown.

    mdBook is used by the Rust programming language project, and The Rust Programming Language book
    is an example.
    """

    icon = "book"
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

    icon = "book-open-reader"
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

        # NB: classically, the docs dir has Makefile enabling `make html`.
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


class MkDocs(ProjectSpec):
    """MkDocs documentation project."""

    icon = "file-alt"
    spec_doc = "https://www.mkdocs.org/user-guide/configuration/"

    _NAMES = {"mkdocs.yml", "mkdocs.yaml"}

    def match(self) -> bool:
        return bool(self._NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server
        from projspec.content.metadata import DescriptiveMetadata

        fname = next(n for n in self._NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        cfg = cfg or {}
        meta: dict[str, str] = {}
        for key in ("site_name", "site_description", "site_author", "repo_url"):
            if val := cfg.get(key):
                meta[key] = str(val)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        site_dir = cfg.get("site_dir", "site")

        arts = AttrDict(
            docs=StaticSite(
                proj=self.proj,
                cmd=["mkdocs", "build"],
                fn=f"{self.proj.url}/{site_dir}/index.html",
            ),
            serve=Server(
                proj=self.proj,
                cmd=["mkdocs", "serve"],
            ),
        )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal MkDocs project."""
        name = os.path.basename(path)
        with open(os.path.join(path, "mkdocs.yml"), "wt") as f:
            f.write(
                f"site_name: {name}\n"
                "\n"
                "nav:\n"
                "  - Home: index.md\n"
                "\n"
                "theme:\n"
                "  name: material\n"
            )
        docs_dir = os.path.join(path, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        with open(os.path.join(docs_dir, "index.md"), "wt") as f:
            f.write(f"# {name}\n\nWelcome to the documentation.\n")


class Sphinx(ProjectSpec):
    """Sphinx documentation project (standalone, without ReadTheDocs config)."""

    icon = "scroll"
    spec_doc = "https://www.sphinx-doc.org/en/master/usage/configuration.html"

    def match(self) -> bool:
        if "conf.py" in self.proj.basenames:
            return True
        # Check docs/conf.py
        docs_conf = f"{self.proj.url}/docs/conf.py"
        try:
            return self.proj.fs.isfile(docs_conf)
        except Exception:
            return False

    def parse(self) -> None:
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server
        from projspec.content.metadata import DescriptiveMetadata

        # Find conf.py
        if "conf.py" in self.proj.basenames:
            conf_path = self.proj.basenames["conf.py"]
            docs_dir = self.proj.url
        else:
            conf_path = f"{self.proj.url}/docs/conf.py"
            docs_dir = f"{self.proj.url}/docs"

        meta: dict[str, str] = {}
        try:
            with self.proj.fs.open(conf_path, "rt") as f:
                content = f.read()
            for var in ("project", "author", "release", "version"):
                m = re.search(
                    rf'^{var}\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE
                )
                if m:
                    meta[var] = m.group(1)
        except Exception:
            pass

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        build_dir = f"{docs_dir}/_build/html"
        arts = AttrDict(
            docs=StaticSite(
                proj=self.proj,
                cmd=["sphinx-build", "-b", "html", docs_dir, build_dir],
                fn=f"{build_dir}/index.html",
            ),
            autobuild=Server(
                proj=self.proj,
                cmd=["sphinx-autobuild", docs_dir, build_dir],
            ),
        )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Sphinx docs project."""
        name = os.path.basename(path)
        docs_dir = os.path.join(path, "docs")
        os.makedirs(docs_dir, exist_ok=True)

        with open(os.path.join(docs_dir, "conf.py"), "wt") as f:
            f.write(
                f'project = "{name}"\n' "extensions = []\n" 'html_theme = "alabaster"\n'
            )
        with open(os.path.join(docs_dir, "index.rst"), "wt") as f:
            f.write(f"{name}\n{'=' * len(name)}\n\n.. toctree::\n   :maxdepth: 2\n")
        with open(os.path.join(docs_dir, "requirements.txt"), "wt") as f:
            f.write("sphinx\n")


class Docusaurus(ProjectSpec):
    """Docusaurus documentation/website project."""

    icon = "dragon"
    spec_doc = "https://docusaurus.io/docs/configuration"

    _CONFIG_NAMES = {
        "docusaurus.config.js",
        "docusaurus.config.ts",
        "docusaurus.config.mjs",
    }

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server
        from projspec.content.metadata import DescriptiveMetadata

        fname = next(n for n in self._CONFIG_NAMES if n in self.proj.basenames)

        meta: dict[str, str] = {}
        try:
            with self.proj.get_file(fname) as f:
                content = f.read()
            for key in (
                "title",
                "tagline",
                "url",
                "organizationName",
                "projectName",
            ):
                m = re.search(rf'{key}\s*:\s*["\']([^"\']+)["\']', content)
                if m:
                    meta[key] = m.group(1)
        except Exception:
            pass

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        pkg_mgr = "yarn" if "yarn.lock" in self.proj.basenames else "npm"
        arts = AttrDict(
            build=StaticSite(
                proj=self.proj,
                cmd=[pkg_mgr, "run", "build"],
                fn=f"{self.proj.url}/build/index.html",
            ),
            start=Server(
                proj=self.proj,
                cmd=[pkg_mgr, "run", "start"],
            ),
        )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Docusaurus project via npx."""
        from projspec.utils import run_subprocess

        name = os.path.basename(path)
        run_subprocess(
            [
                "npx",
                "create-docusaurus@latest",
                name,
                "classic",
                "--skip-install",
            ],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )
