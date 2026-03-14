import os

from projspec.proj import ProjectSpec, ParseFailed
from projspec.utils import _ipynb_to_py, run_subprocess

# TODO: webapp Servers should (optionally?) call threading.Timer(0.5, webbrowser.open(..));
#  but then it must not block, and we need to set/infer the URL including port.


class Django(ProjectSpec):
    """A python web app using the django framework"""

    # this is the metadata settings reference
    spec_doc = "https://docs.djangoproject.com/en/6.0/ref/settings/"

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

    @staticmethod
    def _create(path, sitename="mysite", appname="myapp"):
        os.makedirs(path, exist_ok=True)
        cmd = ["python", "-m", "django", "startproject", sitename, path]
        run_subprocess(cmd, cwd=path, output=False)
        cmd = ["python", f"{path}/manage.py", "startapp", appname]
        run_subprocess(cmd, cwd=path, output=False)


class Streamlit(ProjectSpec):
    """Interactive graphical app served in the browser, with streamlit components"""

    spec_doc = "https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization"
    # see also "https://docs.streamlit.io/develop/api-reference/configuration/config.toml", which is
    # mainly theme and server config.
    server_args = {"port_arg": "--server.address", "address_arg": "--server.port"}

    def match(self) -> bool:
        # more possible layouts
        return bool(
            {".streamlit", "streamlit_app.py"}.intersection(self.proj.basenames)
        )

    @staticmethod
    def _create(path):
        # `streamlit init` does this, without the toml file.
        os.makedirs(f"{path}/.streamlit", exist_ok=True)
        with open(f"{path}/.streamlit/config.toml", "wt") as f:
            f.write(
                """
[global]

[logger]
level = "info"

[server]
headless = true
"""
            )
        with open(f"{path}/streamlit_app.py", "wt") as f:
            f.write(
                """
import streamlit as st
st.title("Streamlit minimal app")
st.write("Hello world!")
"""
            )
        if not os.path.exists(f"{path}/requirements.txt"):
            with open(f"{path}/requirements.txt", "wt") as f:
                f.write("streamlit")
        elif "streamlit" not in open(f"{path}/requirements.txt").read():
            with open(f"{path}/requirements.txt", "at") as f:
                f.write("\nstreamlit")

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
                proj=self.proj,
                cmd=[
                    "streamlit",
                    "run",
                    pyfiles[0].replace(self.proj.url, "").lstrip("/"),
                ],
            )
        else:
            # TODO: use walk (top-down) here to avoid known directories like .venv/
            pyfiles = self.proj.fs.glob(f"{self.proj.url}/**/*.py")
            pycontent = self.proj.fs.cat(pyfiles)
            self.artifacts["server"] = {}
            for path, content in pycontent.items():
                if "import streamlit as st" and "\nst." in content.decode():
                    name = path.rsplit("/", 1)[-1].replace(".py", "")
                    self.artifacts["server"][name] = Server(
                        proj=self.proj,
                        cmd=[
                            "streamlit",
                            "run",
                            path.replace(self.proj.url, "").lstrip("/"),
                        ],
                    )


class Marimo(ProjectSpec):
    """Reactive Python notebook and webapp served in the browser"""

    spec_doc = "https://docs.marimo.io/"
    server_args = {"port_arg": "--port", "address_arg": "--host"}

    def match(self) -> bool:
        return any(fn.endswith(".py") for fn in self.proj.scanned_files)

    def parse(self) -> None:
        from projspec.artifact.process import Server

        self.artifacts["server"] = {}
        for path, content in self.proj.scanned_files.items():
            if not path.endswith(".py"):
                continue
            content = content.decode()
            has_import = "import marimo" in content or "from marimo" in content
            has_app = "marimo.App(" in content or "= App(" in content
            if has_import and has_app:
                name = path.rsplit("/", 1)[-1].replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj, cmd=["marimo", "run", path], **self.server_args
                )

        if not self.artifacts["server"]:
            raise ParseFailed

    @staticmethod
    def _create(path):
        with open(f"{path}/marimo-app.py", "wt") as f:
            f.write(
                """
import marimo
__generated_with = "0.19.11"
app = marimo.App()

@app.cell
def _():
    import marimo as mo
    return "Hello, marimo!"

if __name__ == "__main__":
    app.run()
"""
            )


class Flask(ProjectSpec):
    """Lightweight web application framework in Python"""

    spec_doc = "https://flask.palletsprojects.com/en/stable/config/"
    server_args = {"port_arg": "--port", "address_arg": "--host"}

    def match(self) -> bool:
        # the default and common name for the main file is app.py
        return (
            any(fn.endswith(".py") for fn in self.proj.scanned_files)
            or "app.py" in self.proj.basenames
        )

    def parse(self) -> None:
        from projspec.artifact.process import Server

        self.artifacts["server"] = {}
        for path, content in self.proj.scanned_files.items():
            if not path.endswith(".py"):
                continue
            content = content.decode()
            has_import = "import flask" in content or "from flask" in content
            has_app = "flask.Flask(" in content or "= Flask(" in content
            if has_import and has_app:
                name = path.replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj,
                    cmd=["flask", "--app", name, "run"],
                    **self.server_args,
                )
        # read this one file anyway, if it wasn't already
        if "app.py" in self.proj.basenames and "app.py" not in self.proj.scanned_files:
            content = self.proj.fs.cat("app.py").decode()
            # stash
            self.proj.scanned_files["app.py"] = content
            has_import = "import flask" in content or "from flask" in content
            has_app = "flask.Flask(" in content or "= Flask(" in content
            if has_import and has_app:
                self.artifacts["server"]["app"] = Server(
                    proj=self.proj, cmd=["flask", "run"] ** self.server_args
                )

        if not self.artifacts["server"]:
            raise ParseFailed

    @staticmethod
    def _create(path):
        with open(f"{path}/flask-app.py", "wt") as f:
            # https://flask.palletsprojects.com/en/stable/quickstart/#a-minimal-application
            f.write(
                """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"
"""
            )


class FastAPI(ProjectSpec):
    """Fast web application framework in Python"""

    spec_doc = "https://fastapi.tiangolo.com/advanced/settings/"
    server_args = {"port_arg": "--port", "address_arg": "--host"}

    def match(self) -> bool:
        # the default and common name for the main file is app.py
        return (
            any(fn.endswith(".py") for fn in self.proj.scanned_files)
            or "app.py" in self.proj.basenames
        )

    def parse(self) -> None:
        from projspec.artifact.process import Server

        self.artifacts["server"] = {}
        for path, content in self.proj.scanned_files.items():
            if not path.endswith(".py"):
                continue
            content = content.decode()
            has_import = "import fastapi" in content or "from fastapi" in content
            has_app = "FastAPI(" in content
            if has_import and has_app:
                name = path.rsplit("/", 1)[-1].replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj, cmd=["fastapi", "run", path], **self.server_args
                )

        if not self.artifacts["server"]:
            raise ParseFailed

    @staticmethod
    def _create(path):
        with open(f"{path}/flask-app.py", "wt") as f:
            # https://fastapi.tiangolo.com/#create-it
            f.write(
                """
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
"""
            )


class Dash(ProjectSpec):
    """Interactive data dashboarding with plotly components."""

    spec_doc = "https://dash.plotly.com/tutorial"  # no actual configuration
    server_args = {"in_env": True, "port_arg": "PORT", "address_arg": "HOST"}

    def match(self) -> bool:
        # the default and common name for the main file is app.py
        return (
            any(fn.endswith(".py") for fn in self.proj.scanned_files)
            or "app.py" in self.proj.basenames
        )

    def parse(self) -> None:
        from projspec.artifact.process import Server

        self.artifacts["server"] = {}
        for path, content in self.proj.scanned_files.items():
            if not path.endswith(".py"):
                continue
            content = content.decode()
            has_import = "import dash" in content or "from dash" in content
            has_app = "Dash(" in content
            if has_import and has_app:
                name = path.rsplit("/", 1)[-1].replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj, cmd=["python", path], **self.server_args
                )

        if not self.artifacts["server"]:
            raise ParseFailed

    def _create(path: str) -> None:
        with open(f"{path}/app.py", "wt") as f:
            # https://dash.plotly.com/minimal-app
            f.write(
                """from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import pandas as pd

df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv')

app = Dash()

# Requires Dash 2.17.0 or later
app.layout = [
    html.H1(children='Title of Dash App', style={'textAlign':'center'}),
    dcc.Dropdown(df.country.unique(), 'Canada', id='dropdown-selection'),
    dcc.Graph(id='graph-content')
]

@callback(
    Output('graph-content', 'figure'),
    Input('dropdown-selection', 'value')
)
def update_graph(value):
    dff = df[df.country==value]
    return px.line(dff, x='year', y='pop')

if __name__ == '__main__':
    app.run(debug=True)
"""
            )


class Panel(ProjectSpec):
    """Interactive data dashboarding using panel, with holoviz/bokeh components."""

    spec_doc = "https://panel.holoviz.org/api/config.html"

    def match(self) -> bool:
        # the default and common name for the main file is app.py
        return (
            any(fn.endswith((".py", ".ipynb")) for fn in self.proj.scanned_files)
            or "app.py" in self.proj.basenames
        )

    def parse(self) -> None:
        from projspec.artifact.process import Server

        self.artifacts["server"] = {}
        for path, content in self.proj.scanned_files.items():
            if not path.endswith((".py", ".ipynb")):
                continue
            content = content.decode()
            if path.endswith(".ipynb"):
                content = _ipynb_to_py(content)
            has_import = "import panel" in content or "from panel" in content
            has_app = ".servable(" in content
            if has_import and has_app:
                name = path.rsplit("/", 1)[-1].replace(".py", "")
                self.artifacts["server"][name] = Server(
                    proj=self.proj,
                    cmd=["panel", "serve", path],
                )

        if not self.artifacts["server"]:
            raise ParseFailed

    def _create(path: str) -> None:
        with open(f"{path}/app.py", "wt") as f:
            # https://panel.holoviz.org/tutorials/basic/serve.html#serve-the-app
            f.write(
                """import panel as pn

pn.extension()

pn.panel("Hello World").servable()
"""
            )
