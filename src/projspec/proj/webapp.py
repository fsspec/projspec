from projspec.proj import ProjectSpec, ParseFailed


class Django(ProjectSpec):
    """A python web app using the django framework"""

    def match(self):
        return "manage.py" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Server

        # global settings are in ./*/settings.py in a directory also containing urls.py
        # the top-level; manage.py may have the line to locate it:
        # os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
        # and "mysite" is the suggestion in the tutorials;
        # can also be given as --settings to manage.py
        allpy = self.proj.fs.glob(f"{self.proj.url}/*/*.py")

        # We could also choose to parse the settings or URLs - but they are required
        s_dirs = {_.rsplit("/", 1)[0] for _ in allpy if _.endswith("settings.py")}
        u_dirs = {_.rsplit("/", 1)[0] for _ in allpy if _.endswith("urls.py")}
        maindir = s_dirs.intersection(u_dirs)
        if not maindir:
            raise ParseFailed

        # each site is a subdirectory with admin.py and other stuff, typically
        # each mapped to a different sub-URL.
        appdirs = [_.rsplit("/", 2)[-2] for _ in allpy if _.endswith("admin.py")]
        if appdirs:
            self.contents["apps"] = appdirs

        self.artifacts["server"] = Server(
            proj=self.proj, cmd=["python", "manage.py", "runserver"]
        )


class Streamlit(ProjectSpec):
    """Interactive graphical app served in the browser, with streamlit components"""

    spec_doc = "https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization"
    # see also "https://docs.streamlit.io/develop/api-reference/configuration/config.toml", which is
    # mainly theme and server config.

    def match(self) -> bool:
        # more possible layouts
        return bool(
            {".streamlit", "streamlit_app.py"}.intersection(self.proj.basenames)
        )

    def parse(self) -> None:
        from projspec.content.environment import PythonRequirements, CondaEnv
        from projspec.artifact.process import Server

        # https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies

        # a requirements.txt file is the most common and suggested way, but uv, pipenv and poetry are
        # also supported - but they will get picked up as separate project types.
        # Furthermore, the spec can live alongside the code in subdirectories, the apps in this
        # project do not share an environment.
        if "environment" not in self.proj.contents:
            # just because of ordering
            for cls in (PythonRequirements, CondaEnv):
                if cls.match(self):
                    p = cls(self.proj)
                    p.parse()
                    self._contents["environment"] = p.contents["environment"]
                    break
        if "environment" in self.proj.contents:
            self._contents["environment"] = self.proj.contents["environment"]
        # TODO: packages.txt lists packages to apt-get

        # the common case is a single .py file
        pyfiles = [v for v in self.proj.basenames if v.endswith(".py")]
        if len(pyfiles) == 1:
            self.artifacts["server"] = Server(
                proj=self.proj, cmd=["streamlit", "run", pyfiles[0]]
            )
        else:
            pyfiles = self.proj.fs.glob(f"{self.proj.url}/**/*.py")
            pycontent = self.proj.fs.cat(pyfiles)
            self.artifacts["server"] = {}
            for path, content in pycontent.items():
                if "import streamlit as st" and "\nst." in content.decode():
                    name = path.rsplit("/", 1)[-1].replace(".py", "")
                    self.artifacts["server"][name] = Server(
                        proj=self.proj,
                        cmd=["streamlit", "run", path.replace(self.proj.url, "")],
                    )


class Marimo(ProjectSpec):
    """Reactive Python notebook and webapp served in the browser"""

    spec_doc = "https://docs.marimo.io/"

    def match(self) -> bool:
        # marimo notebooks are .py files with specific imports at the top
        pyfiles = [fn for fn in self.proj.basenames if fn.endswith(".py")]
        if not pyfiles:
            return False
        # quick check for marimo import in any .py file
        for fn in pyfiles:
            path = self.proj.basenames[fn]
            try:
                with self.proj.fs.open(path, "rb") as f:
                    header = f.read(500)
                    if b"import marimo" in header or b"from marimo" in header:
                        return True
            except OSError:
                continue
        return False

    def parse(self) -> None:
        from projspec.artifact.process import Server

        # marimo notebooks contain `import marimo` and `marimo.App(` or `= App(`
        pyfiles = self.proj.fs.glob(f"{self.proj.url}/**/*.py")
        pycontent = self.proj.fs.cat(pyfiles)
        self.artifacts["server"] = {}
        for path, content in pycontent.items():
            content = content.decode()
            has_import = "import marimo" in content or "from marimo" in content
            has_app = "marimo.App(" in content or "= App(" in content
            if has_import and has_app:
                name = path.rsplit("/", 1)[-1].replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj,
                    cmd=["marimo", "run", path.replace(self.proj.url, "").lstrip("/")],
                )

        if not self.artifacts["server"]:
            raise ParseFailed("No marimo notebooks found")


# TODO: the following are similar to streamlit, but with perhaps even less metadata
# - flask (from flask import Flask; app = Flask( )
# - fastapi (from fastapi import FastAPI; app = FastAPI( )
# - plotly/dash (from dash import Dash; app = Dash(); app.run())
# - voila (this is just a way to display a notebook)
# - panel (import panel as pn; .servable())
# Each of these takes extra parameters for listen address and port at least.
