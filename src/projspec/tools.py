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
        # ------------------------------------------------------------------
        # Python ecosystem
        # ------------------------------------------------------------------
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
                "https://www.python.org/downloads/",
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
        # ------------------------------------------------------------------
        # Conda ecosystem
        # ------------------------------------------------------------------
        ToolInfo(
            name="conda",
            description="Cross-platform package and environment manager (Anaconda/Miniconda/Miniforge).",
            install_suggestions=[
                "https://github.com/conda-forge/miniforge#install",
                "https://docs.conda.io/en/latest/miniconda.html",
                "brew install --cask miniforge",
                "winget install --id=Anaconda.Miniconda3",
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
                "https://github.com/prefix-dev/rattler-build/releases",
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
        # ------------------------------------------------------------------
        # Containers
        # ------------------------------------------------------------------
        ToolInfo(
            name="docker",
            description="Container platform for building, shipping, and running applications.",
            install_suggestions=[
                "https://www.docker.com/products/docker-desktop/",
                "brew install --cask docker",
                "sudo apt-get install docker-ce docker-ce-cli containerd.io",
                "sudo dnf install docker-ce docker-ce-cli containerd.io",
            ],
        ),
        # ------------------------------------------------------------------
        # Node / JavaScript ecosystem
        # ------------------------------------------------------------------
        ToolInfo(
            name="node",
            description="JavaScript runtime environment (Node.js).",
            install_suggestions=[
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && nvm install --lts",
                "conda install -c conda-forge nodejs",
                "brew install node",
                "https://nodejs.org/en/download/",
                "winget install --id=OpenJS.NodeJS",
            ],
        ),
        ToolInfo(
            name="npm",
            description="Default package manager bundled with Node.js.",
            install_suggestions=[
                "https://nodejs.org/en/download/",
                "nvm install --lts",
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
                "https://yarnpkg.com/getting-started/install",
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
        # ------------------------------------------------------------------
        # Rust ecosystem
        # ------------------------------------------------------------------
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
        # ------------------------------------------------------------------
        # Version control
        # ------------------------------------------------------------------
        ToolInfo(
            name="git",
            description="Distributed version control system.",
            install_suggestions=[
                "brew install git",
                "sudo apt-get install git",
                "sudo dnf install git",
                "conda install -c conda-forge git",
                "winget install --id=Git.Git",
                "https://git-scm.com/downloads",
            ],
        ),
        # ------------------------------------------------------------------
        # Web frameworks / app runners
        # ------------------------------------------------------------------
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
        # ------------------------------------------------------------------
        # MLOps
        # ------------------------------------------------------------------
        ToolInfo(
            name="mlflow",
            description="Open-source platform for managing the ML lifecycle.",
            install_suggestions=[
                "pip install mlflow",
                "conda install -c conda-forge mlflow",
                "uv add mlflow",
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
