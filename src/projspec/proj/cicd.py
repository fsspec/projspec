"""CI/CD project specs: GitHub Actions, GitLab CI, CircleCI, Taskfile, JustFile, Tox."""

import os

import yaml

from projspec.proj.base import ParseFailed, ProjectSpec, ProjectExtra
from projspec.utils import AttrDict


class GitHubActions(ProjectExtra):
    """GitHub Actions CI/CD workflows

    Each YAML file under .github/workflows/ defines one workflow.
    """

    icon = "🐙"
    spec_doc = "https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions"

    def match(self) -> bool:
        # Check for the .github/workflows directory
        workflows_dir = f"{self.proj.url}/.github/workflows"
        try:
            entries = self.proj.fs.ls(workflows_dir, detail=False)
            return any(e.endswith((".yml", ".yaml")) for e in entries)
        except (FileNotFoundError, NotADirectoryError, Exception):
            return False

    def parse(self) -> None:
        from projspec.content.cicd import CIWorkflow

        workflows_dir = f"{self.proj.url}/.github/workflows"
        try:
            entries = self.proj.fs.ls(workflows_dir, detail=False)
        except Exception as exc:
            raise ParseFailed(f"Could not list .github/workflows: {exc}") from exc

        ci_workflows = AttrDict()
        for entry in entries:
            if not entry.endswith((".yml", ".yaml")):
                continue
            try:
                with self.proj.fs.open(entry, "rt") as f:
                    wf = yaml.safe_load(f)
            except Exception:
                continue
            if not isinstance(wf, dict):
                continue

            name = wf.get(
                "name",
                os.path.basename(entry).replace(".yml", "").replace(".yaml", ""),
            )
            on = wf.get("on", wf.get(True, {}))  # 'on' is a YAML boolean alias
            triggers = []
            if isinstance(on, dict):
                triggers = list(on.keys())
            elif isinstance(on, list):
                triggers = on
            elif isinstance(on, str):
                triggers = [on]

            jobs = list(wf.get("jobs", {}).keys())
            key = name.lower().replace(" ", "_").replace("-", "_")
            ci_workflows[key] = CIWorkflow(
                proj=self.proj,
                name=name,
                triggers=[str(t) for t in triggers],
                jobs=jobs,
                provider="github",
            )

        if not ci_workflows:
            raise ParseFailed("No valid GitHub Actions workflows found")

        self._contents = AttrDict(ci_workflow=ci_workflows)
        self._artifacts = AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal GitHub Actions CI workflow."""
        workflows_dir = os.path.join(path, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        with open(os.path.join(workflows_dir, "ci.yml"), "wt") as f:
            f.write(
                "name: CI\n"
                "\n"
                "on:\n"
                "  push:\n"
                "    branches: [main]\n"
                "  pull_request:\n"
                "    branches: [main]\n"
                "\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - name: Run tests\n"
                "        run: echo 'Add your test command here'\n"
            )


class GitLabCI(ProjectExtra):
    """GitLab CI/CD pipeline defined in .gitlab-ci.yml."""

    icon = "🦊"
    spec_doc = "https://docs.gitlab.com/ci/yaml/"

    def match(self) -> bool:
        return ".gitlab-ci.yml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.cicd import CIWorkflow

        try:
            with self.proj.get_file(".gitlab-ci.yml") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read .gitlab-ci.yml: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(".gitlab-ci.yml did not parse to a mapping")

        stages = cfg.get("stages", [])
        # Jobs are any top-level keys that are not reserved keywords
        reserved = {
            "stages",
            "variables",
            "include",
            "workflow",
            "default",
            "image",
            "services",
            "before_script",
            "after_script",
            "cache",
        }
        jobs = [k for k in cfg if k not in reserved and not k.startswith(".")]

        self._contents = AttrDict(
            ci_workflow=CIWorkflow(
                proj=self.proj,
                name="GitLab CI",
                triggers=stages,
                jobs=jobs,
                provider="gitlab",
            )
        )
        self._artifacts = AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal .gitlab-ci.yml."""
        with open(os.path.join(path, ".gitlab-ci.yml"), "wt") as f:
            f.write(
                "stages:\n"
                "  - test\n"
                "\n"
                "test:\n"
                "  stage: test\n"
                "  script:\n"
                "    - echo 'Add your test command here'\n"
            )


class CircleCI(ProjectExtra):
    """CircleCI pipeline defined in .circleci/config.yml."""

    icon = "⦿"
    spec_doc = "https://circleci.com/docs/configuration-reference/"

    def match(self) -> bool:
        config_path = f"{self.proj.url}/.circleci/config.yml"
        try:
            return self.proj.fs.isfile(config_path)
        except Exception:
            return False

    def parse(self) -> None:
        from projspec.content.cicd import CIWorkflow

        config_path = f"{self.proj.url}/.circleci/config.yml"
        try:
            with self.proj.fs.open(config_path, "rt") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read .circleci/config.yml: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(".circleci/config.yml did not parse to a mapping")

        jobs = list(cfg.get("jobs", {}).keys())
        workflows = cfg.get("workflows", {})
        workflow_names = [k for k in workflows if k != "version"]

        self._contents = AttrDict(
            ci_workflow=CIWorkflow(
                proj=self.proj,
                name="CircleCI",
                triggers=workflow_names,
                jobs=jobs,
                provider="circleci",
            )
        )
        self._artifacts = AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal CircleCI config."""
        circleci_dir = os.path.join(path, ".circleci")
        os.makedirs(circleci_dir, exist_ok=True)
        with open(os.path.join(circleci_dir, "config.yml"), "wt") as f:
            f.write(
                "version: 2.1\n"
                "\n"
                "jobs:\n"
                "  test:\n"
                "    docker:\n"
                "      - image: cimg/base:stable\n"
                "    steps:\n"
                "      - checkout\n"
                "      - run: echo 'Add your test command here'\n"
                "\n"
                "workflows:\n"
                "  main:\n"
                "    jobs:\n"
                "      - test\n"
            )


class Taskfile(ProjectSpec):
    """Task runner using Taskfile (go-task)."""

    icon = "✅"
    spec_doc = "https://taskfile.dev/reference/schema/"

    _NAMES = {"Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"}

    def match(self) -> bool:
        return bool(self._NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        fname = next(n for n in self._NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(f"{fname} did not parse to a mapping")

        tasks = cfg.get("tasks", {})
        cmds = AttrDict()
        arts = AttrDict()
        for task_name, task_def in tasks.items():
            if not task_name or task_name.startswith("_"):
                continue
            cmd = ["task", task_name]
            cmds[task_name] = Command(proj=self.proj, cmd=cmd)
            arts[task_name] = Process(proj=self.proj, cmd=cmd)

        self._contents = AttrDict(command=cmds) if cmds else AttrDict()
        self._artifacts = AttrDict(process=arts) if arts else AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Taskfile.yml."""
        with open(os.path.join(path, "Taskfile.yml"), "wt") as f:
            f.write(
                "version: '3'\n"
                "\n"
                "tasks:\n"
                "  default:\n"
                "    desc: Default task\n"
                "    cmds:\n"
                "      - echo 'Hello from Taskfile!'\n"
                "\n"
                "  test:\n"
                "    desc: Run tests\n"
                "    cmds:\n"
                "      - echo 'Add your test command here'\n"
            )


class JustFile(ProjectSpec):
    """Task runner using Just (justfile / Justfile).

    A justfile defines named recipes that can be run with `just <recipe>`.
    """

    icon = "▶️"
    spec_doc = "https://just.systems/man/en/"

    _NAMES = {"justfile", "Justfile", ".justfile"}

    def match(self) -> bool:
        return bool(self._NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        import re
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        fname = next(n for n in self._NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                text = f.read()
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        # Recipes are lines matching: recipe-name ...: (not starting with #/@/space)
        recipe_names = re.findall(
            r"^([a-zA-Z_][a-zA-Z0-9_-]*)(?:\s.*)?:", text, re.MULTILINE
        )

        cmds = AttrDict()
        arts = AttrDict()
        for name in recipe_names:
            cmd = ["just", name]
            cmds[name] = Command(proj=self.proj, cmd=cmd)
            arts[name] = Process(proj=self.proj, cmd=cmd)

        self._contents = AttrDict(command=cmds) if cmds else AttrDict()
        self._artifacts = AttrDict(process=arts) if arts else AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal justfile."""
        with open(os.path.join(path, "justfile"), "wt") as f:
            f.write(
                "# Default recipe\n"
                "default:\n"
                "    echo 'Hello from just!'\n"
                "\n"
                "# Run tests\n"
                "test:\n"
                "    echo 'Add your test command here'\n"
            )


class Tox(ProjectSpec):
    """Python test automation using tox.

    A set of environments and run commands to be run as a workflow.
    """

    icon = "🧪"
    spec_doc = "https://tox.wiki/en/stable/config.html"

    def match(self) -> bool:
        if "tox.ini" in self.proj.basenames or "tox.toml" in self.proj.basenames:
            return True
        return bool(self.proj.pyproject.get("tool", {}).get("tox"))

    def parse(self) -> None:
        import configparser
        import re
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        env_names: list[str] = []

        if "tox.ini" in self.proj.basenames:
            try:
                with self.proj.get_file("tox.ini") as f:
                    text = f.read()
                cfg = configparser.ConfigParser()
                cfg.read_string(text)
                # envlist can be a comma/space/newline separated list with optional braces
                envlist_raw = cfg.get("tox", "envlist", fallback="")
                if envlist_raw:
                    # Strip braces notation like {py39,py310}-django
                    flat = re.sub(r"\{[^}]*\}", "", envlist_raw)
                    env_names = [
                        e.strip() for e in re.split(r"[,\s]+", flat) if e.strip()
                    ]
                # Also pick up [testenv:*] sections
                for section in cfg.sections():
                    if section.startswith("testenv:"):
                        name = section[len("testenv:") :]
                        if name not in env_names:
                            env_names.append(name)
            except Exception as exc:
                raise ParseFailed(f"Could not parse tox.ini: {exc}") from exc

        elif "tox.toml" in self.proj.basenames:
            try:
                import toml
                from projspec.utils import PickleableTomlDecoder

                with self.proj.get_file("tox.toml", text=False) as f:
                    cfg = toml.loads(f.read().decode(), decoder=PickleableTomlDecoder())
                env_names = list(cfg.get("env", {}).keys())
            except Exception as exc:
                raise ParseFailed(f"Could not parse tox.toml: {exc}") from exc

        else:
            tox_cfg = self.proj.pyproject.get("tool", {}).get("tox", {})
            env_names = list(tox_cfg.get("env", {}).keys())

        cmds = AttrDict()
        arts = AttrDict()
        if not env_names:
            # At minimum expose a generic tox run
            cmds["tox"] = Command(proj=self.proj, cmd=["tox"])
            arts["tox"] = Process(proj=self.proj, cmd=["tox"])
        else:
            for name in env_names:
                cmd = ["tox", "-e", name]
                cmds[name] = Command(proj=self.proj, cmd=cmd)
                arts[name] = Process(proj=self.proj, cmd=cmd)

        self._contents = AttrDict(command=cmds)
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal tox.ini."""
        with open(os.path.join(path, "tox.ini"), "wt") as f:
            f.write(
                "[tox]\n"
                "envlist = py311\n"
                "\n"
                "[testenv]\n"
                "deps = pytest\n"
                "commands = pytest {posargs}\n"
            )
