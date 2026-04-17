"""Data/ML workflow specs: dbt, Quarto, Prefect, Dagster, Kedro, Airflow, Snakemake, Nox."""

import os
import re

import yaml

from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.utils import AttrDict


class Dbt(ProjectSpec):
    """dbt (data build tool) project.

    Detected by ``dbt_project.yml`` at the project root.
    """

    spec_doc = "https://docs.getdbt.com/reference/dbt_project.yml"

    def match(self) -> bool:
        return "dbt_project.yml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.get_file("dbt_project.yml") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read dbt_project.yml: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed("dbt_project.yml did not parse to a mapping")

        meta: dict[str, str] = {}
        for key in ("name", "version", "profile"):
            if val := cfg.get(key):
                meta[key] = str(val)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        # Standard dbt commands
        dbt_cmds = {
            "run": ["dbt", "run"],
            "test": ["dbt", "test"],
            "build": ["dbt", "build"],
            "compile": ["dbt", "compile"],
            "docs_generate": ["dbt", "docs", "generate"],
            "docs_serve": ["dbt", "docs", "serve"],
            "seed": ["dbt", "seed"],
            "snapshot": ["dbt", "snapshot"],
            "source_freshness": ["dbt", "source", "freshness"],
        }

        cmds = AttrDict()
        arts = AttrDict()
        for name, cmd in dbt_cmds.items():
            cmds[name] = Command(proj=self.proj, cmd=cmd)
            arts[name] = Process(proj=self.proj, cmd=cmd)

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal dbt project."""
        name = os.path.basename(path)
        with open(os.path.join(path, "dbt_project.yml"), "wt") as f:
            f.write(
                f"name: '{name}'\n"
                "version: '1.0.0'\n"
                "config-version: 2\n"
                "\n"
                "profile: 'default'\n"
                "\n"
                "model-paths: ['models']\n"
                "seed-paths: ['seeds']\n"
                "test-paths: ['tests']\n"
                "snapshot-paths: ['snapshots']\n"
                "\n"
                "models:\n"
                f"  {name}:\n"
                "    +materialized: view\n"
            )
        os.makedirs(os.path.join(path, "models"), exist_ok=True)
        with open(os.path.join(path, "models", "example.sql"), "wt") as f:
            f.write("SELECT 1 AS id, 'hello' AS greeting\n")


class Quarto(ProjectSpec):
    """Quarto publishing system project.

    Detected by ``_quarto.yml`` / ``_quarto.yaml`` or any ``.qmd`` file at the root.
    """

    spec_doc = "https://quarto.org/docs/reference/projects/core.html"

    def match(self) -> bool:
        if (
            "_quarto.yml" in self.proj.basenames
            or "_quarto.yaml" in self.proj.basenames
        ):
            return True
        return any(n.endswith(".qmd") for n in self.proj.basenames)

    def parse(self) -> None:
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server
        from projspec.content.metadata import DescriptiveMetadata

        cfg: dict = {}
        for fname in ("_quarto.yml", "_quarto.yaml"):
            if fname in self.proj.basenames:
                try:
                    with self.proj.get_file(fname) as f:
                        cfg = yaml.safe_load(f) or {}
                except Exception:
                    pass
                break

        meta: dict[str, str] = {}
        project = cfg.get("project", {})
        for key in ("title", "type"):
            if val := project.get(key):
                meta[key] = str(val)
        book = cfg.get("book", {})
        for key in ("title", "author"):
            if val := book.get(key):
                meta[key] = str(val)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        output_dir = project.get("output-dir", "_site")
        arts = AttrDict(
            render=StaticSite(
                proj=self.proj,
                cmd=["quarto", "render"],
                fn=f"{self.proj.url}/{output_dir}/index.html",
            ),
            preview=Server(
                proj=self.proj,
                cmd=["quarto", "preview"],
            ),
        )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Quarto project."""
        name = os.path.basename(path)
        with open(os.path.join(path, "_quarto.yml"), "wt") as f:
            f.write(
                "project:\n"
                "  type: website\n"
                "\n"
                "website:\n"
                f'  title: "{name}"\n'
                "  navbar:\n"
                "    left:\n"
                "      - href: index.qmd\n"
                "        text: Home\n"
                "\n"
                "format:\n"
                "  html:\n"
                "    theme: cosmo\n"
            )
        with open(os.path.join(path, "index.qmd"), "wt") as f:
            f.write(
                "---\n"
                f'title: "{name}"\n'
                "---\n"
                "\n"
                "Welcome to this Quarto project.\n"
            )


class Prefect(ProjectSpec):
    """Prefect workflow orchestration project.

    Detected by ``prefect.yaml`` at the project root.
    """

    spec_doc = "https://docs.prefect.io/v3/deploy/infrastructure-concepts/prefect-yaml"

    def match(self) -> bool:
        return "prefect.yaml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.cicd import PipelineStage
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.get_file("prefect.yaml") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read prefect.yaml: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed("prefect.yaml did not parse to a mapping")

        meta: dict[str, str] = {}
        if name := cfg.get("name"):
            meta["name"] = str(name)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        # Deployments become pipeline stages
        deployments = cfg.get("deployments", [])
        stages = AttrDict()
        arts = AttrDict()
        cmds = AttrDict()
        for dep in deployments:
            if not isinstance(dep, dict):
                continue
            dep_name = dep.get("name", "default")
            entrypoint = dep.get("entrypoint", "")
            stages[dep_name] = PipelineStage(
                proj=self.proj,
                name=dep_name,
                cmd=["prefect", "deployment", "run", dep_name],
            )
            deploy_cmd = ["prefect", "deploy", "--name", dep_name]
            cmds[dep_name] = Command(proj=self.proj, cmd=deploy_cmd)
            arts[dep_name] = Process(proj=self.proj, cmd=deploy_cmd)

        if stages:
            conts["pipeline_stage"] = stages
        if cmds:
            conts["command"] = cmds

        # Generic run command
        arts["run"] = Process(proj=self.proj, cmd=["prefect", "run"])

        self._contents = conts
        self._artifacts = AttrDict(process=arts)


class Dagster(ProjectSpec):
    """Dagster data orchestration project.

    Detected by ``pyproject.toml`` with ``[tool.dagster]`` section,
    or ``dagster.yaml`` / ``workspace.yaml`` at the project root.
    """

    spec_doc = "https://docs.dagster.io/api/python-api/workspace"

    def match(self) -> bool:
        if self.proj.pyproject.get("tool", {}).get("dagster"):
            return True
        return bool(
            {"dagster.yaml", "workspace.yaml"}.intersection(self.proj.basenames)
        )

    def parse(self) -> None:
        from projspec.artifact.process import Process, Server
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        meta: dict[str, str] = {}
        dagster_cfg = self.proj.pyproject.get("tool", {}).get("dagster", {})
        if isinstance(dagster_cfg, dict):
            if module := dagster_cfg.get("module_name"):
                meta["module"] = str(module)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        # Core commands
        dbt_cmds = {
            "dev": ["dagster", "dev"],
            "materialize": ["dagster", "asset", "materialize", "--select", "*"],
        }
        cmds = AttrDict()
        arts = AttrDict()
        for name, cmd in dbt_cmds.items():
            cmds[name] = Command(proj=self.proj, cmd=cmd)

        arts["dev"] = Server(proj=self.proj, cmd=["dagster", "dev"])
        arts["materialize"] = Process(
            proj=self.proj,
            cmd=["dagster", "asset", "materialize", "--select", "*"],
        )

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts


class Kedro(ProjectSpec):
    """Kedro data science pipeline project.

    Detected by ``pyproject.toml`` with ``[tool.kedro]`` section.
    """

    spec_doc = "https://docs.kedro.org/en/stable/kedro_project_setup/settings.html"

    def match(self) -> bool:
        return bool(self.proj.pyproject.get("tool", {}).get("kedro"))

    def parse(self) -> None:
        from projspec.artifact.process import Process, Server
        from projspec.content.cicd import PipelineStage
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        kedro_cfg = self.proj.pyproject.get("tool", {}).get("kedro", {})

        meta: dict[str, str] = {}
        for key in ("package_name", "project_name", "kedro_init_version"):
            if val := kedro_cfg.get(key):
                meta[key] = str(val)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        # Look for pipeline definitions in src/<package>/pipelines/
        package_name = kedro_cfg.get("package_name", "")
        pipeline_names: list[str] = []
        if package_name:
            pipelines_dir = f"{self.proj.url}/src/{package_name}/pipelines"
            try:
                entries = self.proj.fs.ls(pipelines_dir, detail=False)
                pipeline_names = [
                    os.path.basename(e)
                    for e in entries
                    if self.proj.fs.isdir(e) and not os.path.basename(e).startswith("_")
                ]
            except Exception:
                pass

        cmds = AttrDict()
        arts = AttrDict()
        stages = AttrDict()

        # Default pipeline
        cmds["run"] = Command(proj=self.proj, cmd=["kedro", "run"])
        arts["run"] = Process(proj=self.proj, cmd=["kedro", "run"])

        for pipeline in pipeline_names:
            cmd = ["kedro", "run", "--pipeline", pipeline]
            cmds[pipeline] = Command(proj=self.proj, cmd=cmd)
            arts[pipeline] = Process(proj=self.proj, cmd=cmd)
            stages[pipeline] = PipelineStage(proj=self.proj, name=pipeline, cmd=cmd)

        arts["viz"] = Server(proj=self.proj, cmd=["kedro", "viz", "run"])

        if stages:
            conts["pipeline_stage"] = stages
        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts


class Airflow(ProjectSpec):
    """Apache Airflow workflow orchestration project.

    Detected by a ``dags/`` directory at the project root containing Python files.
    """

    spec_doc = (
        "https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html"
    )

    def match(self) -> bool:
        dags_dir = f"{self.proj.url}/dags"
        try:
            if not self.proj.fs.isdir(dags_dir):
                return False
            entries = self.proj.fs.ls(dags_dir, detail=False)
            return any(e.endswith(".py") for e in entries)
        except Exception:
            return False

    def parse(self) -> None:
        from projspec.artifact.process import Process, Server
        from projspec.content.cicd import PipelineStage
        from projspec.content.executable import Command

        dags_dir = f"{self.proj.url}/dags"
        try:
            entries = self.proj.fs.ls(dags_dir, detail=False)
        except Exception as exc:
            raise ParseFailed(f"Could not list dags/: {exc}") from exc

        stages = AttrDict()
        for entry in entries:
            if not entry.endswith(".py"):
                continue
            dag_name = os.path.basename(entry).replace(".py", "")
            if dag_name.startswith("_"):
                continue
            # Try to extract dag_id from file content
            try:
                with self.proj.fs.open(entry, "rt") as f:
                    content = f.read()
                dag_ids = re.findall(r'dag_id\s*=\s*["\']([^"\']+)["\']', content)
                for dag_id in dag_ids:
                    stages[dag_id] = PipelineStage(
                        proj=self.proj,
                        name=dag_id,
                        cmd=["airflow", "dags", "trigger", dag_id],
                    )
            except Exception:
                stages[dag_name] = PipelineStage(
                    proj=self.proj,
                    name=dag_name,
                    cmd=["airflow", "dags", "trigger", dag_name],
                )

        cmds = AttrDict(
            standalone=Command(proj=self.proj, cmd=["airflow", "standalone"]),
            scheduler=Command(proj=self.proj, cmd=["airflow", "scheduler"]),
            webserver=Command(proj=self.proj, cmd=["airflow", "webserver"]),
        )
        arts = AttrDict(
            standalone=Process(proj=self.proj, cmd=["airflow", "standalone"]),
            webserver=Server(
                proj=self.proj, cmd=["airflow", "webserver", "--port", "8080"]
            ),
        )

        conts = AttrDict(command=cmds)
        if stages:
            conts["pipeline_stage"] = stages

        self._contents = conts
        self._artifacts = arts


class Snakemake(ProjectSpec):
    """Snakemake workflow management system project.

    Detected by a ``Snakefile`` or ``workflow/Snakefile`` at the project root.
    """

    spec_doc = (
        "https://snakemake.readthedocs.io/en/stable/snakefiles/configuration.html"
    )

    def match(self) -> bool:
        if "Snakefile" in self.proj.basenames:
            return True
        # also detect workflow/Snakefile layout
        workflow_snakefile = f"{self.proj.url}/workflow/Snakefile"
        try:
            return self.proj.fs.isfile(workflow_snakefile)
        except Exception:
            return False

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.cicd import PipelineStage
        from projspec.content.executable import Command

        # Determine snakefile path
        if "Snakefile" in self.proj.basenames:
            snakefile_path = "Snakefile"
        else:
            snakefile_path = "workflow/Snakefile"

        # Parse rules from snakefile
        rule_names: list[str] = []
        try:
            with self.proj.get_file(snakefile_path) as f:
                content = f.read()
            rule_names = re.findall(r"^rule\s+(\w+)\s*:", content, re.MULTILINE)
        except Exception:
            pass  # rules are optional — we still expose the run command

        cmds = AttrDict()
        arts = AttrDict()
        stages = AttrDict()

        # Generic run command
        run_cmd = ["snakemake", "--cores", "all"]
        cmds["run"] = Command(proj=self.proj, cmd=run_cmd)
        arts["run"] = Process(proj=self.proj, cmd=run_cmd)

        for rule in rule_names:
            if rule in ("all", "clean"):
                continue
            cmd = ["snakemake", rule, "--cores", "all"]
            cmds[rule] = Command(proj=self.proj, cmd=cmd)
            stages[rule] = PipelineStage(proj=self.proj, name=rule, cmd=cmd)

        if stages:
            self._contents = AttrDict(command=cmds, pipeline_stage=stages)
        else:
            self._contents = AttrDict(command=cmds)
        self._artifacts = AttrDict(process=arts)


class Nox(ProjectSpec):
    """Nox Python automation project.

    Detected by ``noxfile.py`` at the project root.
    """

    spec_doc = "https://nox.thea.codes/en/stable/config.html"

    def match(self) -> bool:
        return "noxfile.py" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        # Discover session names via regex on noxfile.py
        session_names: list[str] = []
        try:
            with self.proj.get_file("noxfile.py") as f:
                content = f.read()
            # Sessions are decorated functions: @nox.session or @session
            session_names = re.findall(
                r"@(?:nox\.)?session(?:\([^)]*\))?\s+def\s+(\w+)",
                content,
                re.MULTILINE,
            )
        except Exception:
            pass

        cmds = AttrDict()
        arts = AttrDict()

        if not session_names:
            cmds["nox"] = Command(proj=self.proj, cmd=["nox"])
            arts["nox"] = Process(proj=self.proj, cmd=["nox"])
        else:
            for name in session_names:
                cmd = ["nox", "-s", name]
                cmds[name] = Command(proj=self.proj, cmd=cmd)
                arts[name] = Process(proj=self.proj, cmd=cmd)

        self._contents = AttrDict(command=cmds)
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal noxfile.py."""
        with open(os.path.join(path, "noxfile.py"), "wt") as f:
            f.write(
                "import nox\n"
                "\n"
                "\n"
                "@nox.session\n"
                "def tests(session):\n"
                '    """Run the test suite."""\n'
                "    session.install('pytest')\n"
                "    session.run('pytest')\n"
                "\n"
                "\n"
                "@nox.session\n"
                "def lint(session):\n"
                '    """Lint the code."""\n'
                "    session.install('ruff')\n"
                "    session.run('ruff', 'check', '.')\n"
            )


class Metaflow(ProjectSpec):
    """Metaflow ML/data science workflow project.

    Metaflow has no project-level config file; detection is done by scanning
    Python files for ``from metaflow import`` (or ``import metaflow``) combined
    with a ``FlowSpec`` subclass definition.

    Each ``.py`` file containing a flow becomes a separate ``Command`` /
    ``Process`` pair keyed by the file stem.  If a ``@project(name=...)``
    decorator is found, the project name is captured in metadata.  If
    ``@schedule`` or ``@trigger`` decorators are present, deployment commands
    for Argo Workflows and AWS Step Functions are added alongside the local
    ``run`` command.
    """

    spec_doc = "https://docs.metaflow.org"

    _IMPORT_RE = re.compile(r"from\s+metaflow\s+import|import\s+metaflow")
    _FLOW_RE = re.compile(r"class\s+(\w+)\s*\(\s*\w*FlowSpec\s*\)")
    _PROJECT_RE = re.compile(r'@project\s*\(\s*name\s*=\s*["\']([^"\']+)["\']')
    _STEP_RE = re.compile(r"@step\s+def\s+(\w+)\s*\(")
    _DEPLOY_RE = re.compile(r"@schedule|@trigger|@trigger_on_finish|@project")

    def match(self) -> bool:
        for path, content in self.proj.scanned_files.items():
            if not path.endswith(".py"):
                continue
            try:
                src = content.decode()
            except Exception:
                continue
            if self._IMPORT_RE.search(src) and self._FLOW_RE.search(src):
                return True
        return False

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.cicd import PipelineStage
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        cmds = AttrDict()
        arts = AttrDict()
        stages = AttrDict()
        project_names: list[str] = []

        for full_path, content in self.proj.scanned_files.items():
            if not full_path.endswith(".py"):
                continue
            try:
                src = content.decode()
            except Exception:
                continue

            if not (self._IMPORT_RE.search(src) and self._FLOW_RE.search(src)):
                continue

            # Relative path for use in commands
            rel = full_path.replace(self.proj.url, "").lstrip("/")
            stem = os.path.basename(rel).replace(".py", "")

            # Flow class name and @project name
            flow_match = self._FLOW_RE.search(src)
            flow_class = flow_match.group(1) if flow_match else stem

            proj_match = self._PROJECT_RE.search(src)
            if proj_match:
                project_names.append(proj_match.group(1))

            # Step names → pipeline stages
            step_names = self._STEP_RE.findall(src)
            for step in step_names:
                stage_key = f"{stem}.{step}"
                stages[stage_key] = PipelineStage(
                    proj=self.proj,
                    name=step,
                    cmd=["python", rel, "run", f"--start", step],
                )

            # Local run command
            run_cmd = ["python", rel, "run"]
            cmds[stem] = Command(proj=self.proj, cmd=run_cmd)
            arts[stem] = Process(proj=self.proj, cmd=run_cmd)

            # Deployment commands — only when scheduling/trigger decorators present
            if self._DEPLOY_RE.search(src):
                arts[f"{stem}.argo_create"] = Process(
                    proj=self.proj,
                    cmd=["python", rel, "argo-workflows", "create"],
                )
                arts[f"{stem}.step_functions_create"] = Process(
                    proj=self.proj,
                    cmd=["python", rel, "step-functions", "create"],
                )

        if not cmds:
            raise ParseFailed("No Metaflow flows found in scanned files")

        conts = AttrDict()
        meta: dict[str, str] = {}
        if project_names:
            meta["project"] = ", ".join(sorted(set(project_names)))
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )
        if stages:
            conts["pipeline_stage"] = stages
        conts["command"] = cmds

        self._contents = conts
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Metaflow project with a single HelloFlow."""
        name = os.path.basename(path).replace("-", "_").replace(" ", "_")
        flow_name = "".join(part.title() for part in name.split("_")) + "Flow"
        with open(os.path.join(path, "flow.py"), "wt") as f:
            f.write(
                "from metaflow import FlowSpec, step\n"
                "\n"
                "\n"
                f"class {flow_name}(FlowSpec):\n"
                f'    """{flow_name} — generated by projspec."""\n'
                "\n"
                "    @step\n"
                "    def start(self):\n"
                '        """Entry point."""\n'
                "        print('Starting flow')\n"
                "        self.next(self.end)\n"
                "\n"
                "    @step\n"
                "    def end(self):\n"
                '        """Final step."""\n'
                "        print('Flow complete')\n"
                "\n"
                "\n"
                "if __name__ == '__main__':\n"
                f"    {flow_name}()\n"
            )
