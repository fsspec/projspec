from dataclasses import dataclass, field


@dataclass
class ToolInfo:
    """Information about an external CLI tool referenced by projspec.

    Attributes
    ----------
    name:
        Canonical tool name (the executable that is invoked).
    description:
        One-line description of what the tool does.
    install_suggestions:
        Ordered list of install commands as strings, from most to least
        recommended.
    """

    name: str
    description: str
    install_suggestions: list[str] = field(default_factory=list)


TOOLS: dict[str, ToolInfo] = {
    t.name: t
    for t in [
        ToolInfo(
            name="uv",
            description="Extremely fast Python package and project manager (pip/venv/build replacement).",
            install_suggestions=[
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                "pip install uv",
                "conda install -c conda-forge uv",
                "brew install uv",
                "winget install --id=astral-sh.uv",
            ],
        ),
        ToolInfo(
            name="python",
            description="CPython interpreter; also used as 'python -m build', 'python -m django', etc.",
            install_suggestions=[
                "uv python install 3.12",
                "conda install python=3.12",
                "brew install python",
                "winget install --id=Python.Python.3",
            ],
        ),
        ToolInfo(
            name="poetry",
            description="Dependency management and packaging tool for Python projects.",
            install_suggestions=[
                "curl -sSL https://install.python-poetry.org | python3 -",
                "pip install poetry",
                "conda install -c conda-forge poetry",
                "brew install poetry",
                "pipx install poetry",
            ],
        ),
        ToolInfo(
            name="pre-commit",
            description="Framework for managing and running git pre-commit hooks.",
            install_suggestions=[
                "pip install pre-commit",
                "conda install -c conda-forge pre-commit",
                "brew install pre-commit",
                "pipx install pre-commit",
            ],
        ),
        ToolInfo(
            name="conda",
            description="Cross-platform package and environment manager (Anaconda/Miniconda/Miniforge).",
            install_suggestions=[
                "brew install --cask miniforge",
                "winget install --id=Anaconda.Miniconda3",
                (
                    "mkdir -p ~/miniconda3 && wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh "
                    "&& bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3 && rm -rf ~/miniconda3/miniconda.sh "
                    "&& ~/miniconda3/bin/conda init bash"
                ),
            ],
        ),
        ToolInfo(
            name="conda-build",
            description="Tool for building conda packages from recipes.",
            install_suggestions=[
                "conda install -c conda-forge conda-build",
                "mamba install -c conda-forge conda-build",
            ],
        ),
        ToolInfo(
            name="rattler-build",
            description="Fast, modern conda package builder based on the rattler toolchain.",
            install_suggestions=[
                "conda install -c conda-forge rattler-build",
                "cargo install rattler-build",
                "brew install rattler-build",
            ],
        ),
        ToolInfo(
            name="pixi",
            description="Fast, cross-platform package manager and task runner built on conda.",
            install_suggestions=[
                "curl -fsSL https://pixi.sh/install.sh | bash",
                "brew install pixi",
                "winget install --id=prefix-dev.pixi",
                "conda install -c conda-forge pixi",
            ],
        ),
        ToolInfo(
            name="docker",
            description="Container platform for building, shipping, and running applications.",
            install_suggestions=[
                "brew install --cask docker",
                "sudo apt-get install docker-ce docker-ce-cli containerd.io",
                "sudo dnf install docker-ce docker-ce-cli containerd.io",
            ],
        ),
        ToolInfo(
            name="node",
            description="JavaScript runtime environment (Node.js).",
            install_suggestions=[
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && nvm install --lts",
                "conda install -c conda-forge nodejs",
                "brew install node",
                "winget install --id=OpenJS.NodeJS",
            ],
        ),
        ToolInfo(
            name="npm",
            description="Default package manager bundled with Node.js.",
            install_suggestions=[
                "nvm install --lts",
                "brew install node",
                "conda install -c conda-forge nodejs",
            ],
        ),
        ToolInfo(
            name="yarn",
            description="Fast, reliable JavaScript package manager (alternative to npm).",
            install_suggestions=[
                "npm install -g yarn",
                "brew install yarn",
                "conda install -c conda-forge yarn",
            ],
        ),
        ToolInfo(
            name="jlpm",
            description="JupyterLab's bundled package manager (a pinned yarn wrapper).",
            install_suggestions=[
                "pip install jupyterlab",
                "conda install -c conda-forge jupyterlab",
            ],
        ),
        ToolInfo(
            name="copier",
            description="Library and CLI tool for rendering projects from templates.",
            install_suggestions=[
                "pip install copier",
                "pipx install copier",
                "conda install -c conda-forge copier",
                "brew install copier",
            ],
        ),
        ToolInfo(
            name="cargo",
            description="Rust package manager and build tool.",
            install_suggestions=[
                "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
                "brew install rust",
                "conda install -c conda-forge rust",
                "winget install --id=Rustlang.Rustup",
            ],
        ),
        ToolInfo(
            name="maturin",
            description="Build and publish Rust extensions for Python using PyO3 or rust-cpython.",
            install_suggestions=[
                "pip install maturin",
                "pipx install maturin",
                "conda install -c conda-forge maturin",
                "cargo install maturin",
            ],
        ),
        ToolInfo(
            name="git",
            description="Distributed version control system.",
            install_suggestions=[
                "brew install git",
                "sudo apt-get install git",
                "sudo dnf install git",
                "conda install -c conda-forge git",
                "winget install --id=Git.Git",
            ],
        ),
        ToolInfo(
            name="streamlit",
            description="Framework for turning Python scripts into shareable web apps.",
            install_suggestions=[
                "pip install streamlit",
                "conda install -c conda-forge streamlit",
                "uv add streamlit",
            ],
        ),
        ToolInfo(
            name="marimo",
            description="Reactive Python notebook that doubles as an interactive web app.",
            install_suggestions=[
                "pip install marimo",
                "conda install -c conda-forge marimo",
                "uv add marimo",
                "pipx install marimo",
            ],
        ),
        ToolInfo(
            name="flask",
            description="Lightweight WSGI web application framework for Python.",
            install_suggestions=[
                "pip install flask",
                "conda install -c conda-forge flask",
                "uv add flask",
            ],
        ),
        ToolInfo(
            name="fastapi",
            description="Modern, fast (high-performance) web framework for building APIs with Python.",
            install_suggestions=[
                "pip install 'fastapi[standard]'",
                "conda install -c conda-forge fastapi",
                "uv add 'fastapi[standard]'",
            ],
        ),
        ToolInfo(
            name="panel",
            description="High-level data exploration and web app framework for Python.",
            install_suggestions=[
                "pip install panel",
                "conda install -c conda-forge panel",
                "uv add panel",
            ],
        ),
        ToolInfo(
            name="pyscript",
            description="Framework for running Python in the browser via WebAssembly.",
            install_suggestions=[
                "pip install pyscript",
                "uv add pyscript",
                "conda install -c conda-forge pyscript",
            ],
        ),
        ToolInfo(
            name="briefcase",
            description="Tool for converting a Python project into a standalone native application.",
            install_suggestions=[
                "pip install briefcase",
                "uv add briefcase",
                "conda install -c conda-forge briefcase",
            ],
        ),
        ToolInfo(
            name="mlflow",
            description="Open-source platform for managing the ML lifecycle.",
            install_suggestions=[
                "pip install mlflow",
                "conda install -c conda-forge mlflow",
                "uv add mlflow",
            ],
        ),
        ToolInfo(
            name="task",
            description="Task runner / build tool using Taskfile.yml (go-task).",
            install_suggestions=[
                "brew install go-task",
                "conda install -c conda-forge go-task",
                'sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin',
                "winget install --id=Task.Task",
            ],
        ),
        ToolInfo(
            name="just",
            description="Command runner for project-specific scripts defined in a justfile.",
            install_suggestions=[
                "brew install just",
                "conda install -c conda-forge just",
                "cargo install just",
                "winget install --id=Casey.Just",
            ],
        ),
        ToolInfo(
            name="tox",
            description="Generic Python test automation and virtualenv management tool.",
            install_suggestions=[
                "pip install tox",
                "pipx install tox",
                "conda install -c conda-forge tox",
                "uv tool install tox",
            ],
        ),
        ToolInfo(
            name="nox",
            description="Flexible Python test automation, similar to tox but using plain Python.",
            install_suggestions=[
                "pip install nox",
                "pipx install nox",
                "conda install -c conda-forge nox",
                "uv tool install nox",
            ],
        ),
        ToolInfo(
            name="dbt",
            description="Data transformation tool that runs SQL models against a data warehouse.",
            install_suggestions=[
                "pip install dbt-core",
                "uv add dbt-core",
                "conda install -c conda-forge dbt-core",
            ],
        ),
        ToolInfo(
            name="quarto",
            description="Open-source scientific and technical publishing system.",
            install_suggestions=[
                "brew install --cask quarto",
                "conda install -c conda-forge quarto",
                "winget install --id=Posit.Quarto",
            ],
        ),
        ToolInfo(
            name="prefect",
            description="Workflow orchestration platform for data and ML pipelines.",
            install_suggestions=[
                "pip install prefect",
                "uv add prefect",
                "conda install -c conda-forge prefect",
            ],
        ),
        ToolInfo(
            name="dagster",
            description="Cloud-native data orchestration platform for data pipelines.",
            install_suggestions=[
                "pip install dagster dagster-webserver",
                "uv add dagster dagster-webserver",
                "conda install -c conda-forge dagster",
            ],
        ),
        ToolInfo(
            name="kedro",
            description="Framework for creating reproducible, maintainable data science pipelines.",
            install_suggestions=[
                "pip install kedro",
                "uv add kedro",
                "conda install -c conda-forge kedro",
                "pipx install kedro",
            ],
        ),
        ToolInfo(
            name="airflow",
            description="Platform for programmatically authoring, scheduling, and monitoring workflows.",
            install_suggestions=[
                "pip install apache-airflow",
                "uv add apache-airflow",
                "conda install -c conda-forge apache-airflow",
            ],
        ),
        ToolInfo(
            name="snakemake",
            description="Workflow management system for reproducible and scalable data analyses.",
            install_suggestions=[
                "pip install snakemake",
                "conda install -c conda-forge -c bioconda snakemake",
                "uv add snakemake",
                "mamba install -c conda-forge -c bioconda snakemake",
            ],
        ),
        ToolInfo(
            name="mkdocs",
            description="Static site generator for project documentation, written in Python.",
            install_suggestions=[
                "pip install mkdocs",
                "uv add mkdocs",
                "conda install -c conda-forge mkdocs",
                "pipx install mkdocs",
            ],
        ),
        ToolInfo(
            name="sphinx-build",
            description="Sphinx documentation builder (invoked as sphinx-build).",
            install_suggestions=[
                "pip install sphinx",
                "uv add sphinx",
                "conda install -c conda-forge sphinx",
                "pipx install sphinx",
            ],
        ),
        ToolInfo(
            name="sphinx-autobuild",
            description="Live-reloading Sphinx documentation server.",
            install_suggestions=[
                "pip install sphinx-autobuild",
                "uv add sphinx-autobuild",
                "conda install -c conda-forge sphinx-autobuild",
            ],
        ),
        ToolInfo(
            name="mdbook",
            description="Utility to create modern online books from Markdown files (used by the Rust project).",
            install_suggestions=[
                "cargo install mdbook",
                "brew install mdbook",
                "conda install -c conda-forge mdbook",
            ],
        ),
        ToolInfo(
            name="terraform",
            description="Infrastructure as Code tool by HashiCorp for provisioning cloud resources.",
            install_suggestions=[
                "brew install terraform",
                "conda install -c conda-forge terraform",
                "winget install --id=Hashicorp.Terraform",
            ],
        ),
        ToolInfo(
            name="ansible-playbook",
            description="Ansible playbook runner for automating configuration and deployment.",
            install_suggestions=[
                "pip install ansible",
                "uv add ansible",
                "conda install -c conda-forge ansible",
                "brew install ansible",
                "pipx install ansible",
            ],
        ),
        ToolInfo(
            name="pulumi",
            description="Infrastructure as Code platform supporting multiple languages.",
            install_suggestions=[
                "curl -fsSL https://get.pulumi.com | sh",
                "brew install pulumi/tap/pulumi",
                "conda install -c conda-forge pulumi",
                "winget install --id=Pulumi.Pulumi",
            ],
        ),
        ToolInfo(
            name="cdk",
            description="AWS Cloud Development Kit CLI for defining cloud infrastructure in code.",
            install_suggestions=[
                "npm install -g aws-cdk",
                "npx aws-cdk@latest",
            ],
        ),
        ToolInfo(
            name="earthly",
            description="Build automation tool combining Makefile and Dockerfile syntax.",
            install_suggestions=[
                "brew install earthly/earthly/earthly",
                "sudo /bin/sh -c 'wget https://github.com/earthly/earthly/releases/latest/download/earthly-linux-amd64 -O /usr/local/bin/earthly && chmod +x /usr/local/bin/earthly'",
                "winget install --id=Earthly.Earthly",
            ],
        ),
        ToolInfo(
            name="nixpacks",
            description="Build app source code into OCI images using Nix, without a Dockerfile.",
            install_suggestions=[
                "curl -sSL https://nixpacks.com/install.sh | bash",
                "brew install railwayapp/tap/nixpacks",
            ],
        ),
        ToolInfo(
            name="vagrant",
            description="Tool for building and managing portable virtual machine environments.",
            install_suggestions=[
                "brew install --cask vagrant",
                "winget install --id=Hashicorp.Vagrant",
                "conda install -c conda-forge vagrant",
            ],
        ),
        ToolInfo(
            name="pnpm",
            description="Fast, disk-efficient Node.js package manager.",
            install_suggestions=[
                "npm install -g pnpm",
                "brew install pnpm",
                "winget install --id=pnpm.pnpm",
            ],
        ),
        ToolInfo(
            name="bun",
            description="Fast all-in-one JavaScript runtime, bundler, and package manager.",
            install_suggestions=[
                "curl -fsSL https://bun.sh/install | bash",
                "brew install oven-sh/bun/bun",
                "winget install --id=Oven-sh.Bun",
            ],
        ),
        ToolInfo(
            name="deno",
            description="Secure JavaScript/TypeScript runtime built on V8.",
            install_suggestions=[
                "curl -fsSL https://deno.land/install.sh | sh",
                "brew install deno",
                "conda install -c conda-forge deno",
                "winget install --id=DenoLand.Deno",
            ],
        ),
        ToolInfo(
            name="npx",
            description="Node.js package runner bundled with npm; executes packages without installing.",
            install_suggestions=[
                "nvm install --lts",
                "conda install -c conda-forge nodejs",
            ],
        ),
        ToolInfo(
            name="shiny",
            description="Shiny for Python — build interactive web apps from Python scripts.",
            install_suggestions=[
                "pip install shiny",
                "uv add shiny",
                "conda install -c conda-forge shiny",
            ],
        ),
    ]
}


def suggest(tool_name: str) -> str:
    """Return a formatted string of install suggestions for *tool_name*.

    Parameters
    ----------
    tool_name:
        The executable name as it appears in ``TOOLS`` (e.g. ``"uv"``).

    Returns
    -------
    str
        A multi-line string ready for printing, or a short message when the
        tool is not found in the registry.

    Example
    -------
    >>> print(suggest("uv"))
    uv — Extremely fast Python package and project manager (pip/venv/build replacement).
    Install suggestions:
      curl -LsSf https://astral.sh/uv/install.sh | sh
      pip install uv
      conda install -c conda-forge uv
      brew install uv
      winget install --id=astral-sh.uv
    """
    info = TOOLS.get(tool_name)
    if info is None:
        return f"No install information found for tool: {tool_name!r}"

    lines = [
        f"{info.name} — {info.description}",
        "Install suggestions:",
    ]
    for command in info.install_suggestions:
        lines.append(f"  {command}")
    return "\n".join(lines)
