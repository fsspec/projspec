"""Adapter for the legacy ``anaconda-project.yml`` manifest format."""

import os

import yaml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


_MANIFESTS = ("anaconda-project.yml", "anaconda-project.yaml")
_LOCKS = ("anaconda-project-lock.yml", "anaconda-project-lock.yaml")


class AnacondaProject(ProjectSpec):
    """Legacy Anaconda Project format (``anaconda-project.yml``).

    The project format used by Anaconda Enterprise / Anaconda Workbench and
    the ``anaconda-project`` CLI. Recognised by the ``anaconda-project.yml``
    (or ``anaconda-project.yaml``) manifest at the project root; the sibling
    ``anaconda-project-lock.yml`` holds per-env-spec, per-platform locked
    package lists.

    Reference: https://anaconda-project.readthedocs.io/en/latest/user-guide/reference.html
    """

    icon = "🅰"
    spec_doc = (
        "https://anaconda-project.readthedocs.io/en/latest/user-guide/reference.html"
    )

    def match(self) -> bool:
        return any(n in self.proj.basenames for n in _MANIFESTS)

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.artifact.python_env import CondaEnv, LockFile
        from projspec.content.environment import Environment, Precision, Stack
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        manifest_name = next(n for n in _MANIFESTS if n in self.proj.basenames)
        with self.proj.get_file(manifest_name, text=True) as f:
            meta = yaml.safe_load(f) or {}

        lock_name = next((n for n in _LOCKS if n in self.proj.basenames), None)
        lock_data = None
        if lock_name:
            with self.proj.get_file(lock_name, text=True) as f:
                lock_data = yaml.safe_load(f) or {}

        top_channels = list(meta.get("channels", []) or [])
        top_conda, top_pip = _split_pip(meta.get("packages") or meta.get("dependencies") or [])
        top_platforms = list(meta.get("platforms", []) or [])

        raw_env_specs = meta.get("env_specs") or {}
        if not raw_env_specs:
            # anaconda-project implies a ``default`` env_spec when none is
            # declared (see the reference guide: "creates an environment in
            # envs/default by default").
            raw_env_specs = {"default": {}}
        resolved_specs = _resolve_inheritance(raw_env_specs)

        envs = AttrDict()
        runtimes = AttrDict()
        locks = AttrDict()
        cmds = AttrDict()
        procs = AttrDict()

        for env_name, spec in resolved_specs.items():
            env_conda, env_pip = _split_pip(spec.get("packages") or [])
            channels = _merge(top_channels, spec.get("channels") or [])
            conda_packages = _merge(top_conda, env_conda)
            pip_packages = _merge(top_pip, env_pip)

            envs[env_name] = Environment(
                proj=self.proj,
                channels=channels,
                packages=conda_packages,
                stack=Stack.CONDA,
                precision=Precision.SPEC,
            )
            if pip_packages:
                envs[f"{env_name}.pip"] = Environment(
                    proj=self.proj,
                    channels=[],
                    packages=pip_packages,
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                )

            runtimes[env_name] = CondaEnv(
                proj=self.proj,
                fn=f"{self.proj.url}/envs/{env_name}",
                cmd=["anaconda-project", "prepare", "--env-spec", env_name],
            )
            locks[env_name] = LockFile(
                proj=self.proj,
                fn=f"{self.proj.url}/anaconda-project-lock.yml",
                cmd=["anaconda-project", "lock", "--env-spec", env_name],
            )

            if lock_data is not None:
                locked_pkgs = _lock_packages_for(
                    lock_data, env_name, spec_platforms=spec.get("platforms") or top_platforms
                )
                if locked_pkgs:
                    envs[f"{env_name}.lock"] = Environment(
                        proj=self.proj,
                        channels=[],
                        packages=locked_pkgs,
                        stack=Stack.CONDA,
                        precision=Precision.LOCK,
                    )

        command_kinds = {}
        command_env_specs = {}
        command_http = {}
        for cname, cspec in (meta.get("commands") or {}).items():
            shell = _command_shell(cspec, command_kinds, cname)
            if shell is None:
                continue
            cmds[cname] = Command(proj=self.proj, cmd=shell)
            procs[cname] = Process(
                proj=self.proj,
                cmd=["anaconda-project", "run", cname],
            )
            if isinstance(cspec, dict):
                if cspec.get("env_spec"):
                    command_env_specs[cname] = cspec["env_spec"]
                if cspec.get("supports_http_options"):
                    command_http[cname] = True

        var_content = _variables_content(meta.get("variables") or {}, self.proj)

        extras = _collect_extras(
            meta,
            command_kinds=command_kinds,
            command_env_specs=command_env_specs,
            command_http=command_http,
            lock_enabled=(lock_data or {}).get("locking_enabled") if lock_data else None,
        )

        conts = AttrDict(environment=envs, command=cmds)
        if var_content is not None:
            conts["environment_variables"] = var_content
        if extras:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=extras
            )

        arts = AttrDict(conda_env=runtimes, lock_file=locks, process=procs)

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        name = os.path.basename(path.rstrip("/")) or "project"
        with open(f"{path}/anaconda-project.yml", "wt") as f:
            f.write(
                f"""name: {name}
description: ""

packages:
  - python

platforms:
  - linux-64
  - osx-64
  - osx-arm64
  - win-64

env_specs:
  default: {{}}

commands: {{}}

variables: {{}}
"""
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge(base: list, extra: list) -> list:
    """Append items from *extra* to *base* preserving order, no duplicates."""
    out = list(base)
    for item in extra:
        if item not in out:
            out.append(item)
    return out


def _split_pip(packages):
    """Split an anaconda-project ``packages:`` list into (conda, pip) parts.

    ``packages`` entries are strings; a dict with a single ``pip:`` key holds a
    list of pip requirement specifiers.
    """
    conda, pip = [], []
    for item in packages or []:
        if isinstance(item, dict) and "pip" in item:
            for p in item.get("pip") or []:
                if p not in pip:
                    pip.append(p)
        elif isinstance(item, str):
            if item not in conda:
                conda.append(item)
    return conda, pip


def _resolve_inheritance(raw_specs: dict) -> dict:
    """Flatten ``inherit_from`` chains, merging packages/channels/platforms additively.

    Parents are resolved first; child overrides nothing, only extends. Cycles
    are broken by treating already-visited specs as terminal.
    """
    resolved: dict[str, dict] = {}

    def resolve(name: str, stack: tuple[str, ...]) -> dict:
        if name in resolved:
            return resolved[name]
        if name in stack:
            return dict(raw_specs.get(name) or {})
        spec = dict(raw_specs.get(name) or {})
        parents = spec.pop("inherit_from", None)
        if parents is None:
            resolved[name] = spec
            return spec
        if isinstance(parents, str):
            parents = [parents]
        merged_packages: list = []
        merged_channels: list = []
        merged_platforms: list = []
        for p in parents:
            if p not in raw_specs:
                continue
            r = resolve(p, stack + (name,))
            merged_packages = _merge(merged_packages, r.get("packages") or [])
            merged_channels = _merge(merged_channels, r.get("channels") or [])
            merged_platforms = _merge(merged_platforms, r.get("platforms") or [])
        out = dict(spec)
        out["packages"] = _merge(merged_packages, spec.get("packages") or [])
        out["channels"] = _merge(merged_channels, spec.get("channels") or [])
        plat = _merge(merged_platforms, spec.get("platforms") or [])
        if plat:
            out["platforms"] = plat
        resolved[name] = out
        return out

    for name in raw_specs:
        resolve(name, ())
    return resolved


def _lock_packages_for(lock_data: dict, env_name: str, spec_platforms: list) -> list:
    """Extract a flat, deduplicated list of locked package strings for *env_name*.

    The ``anaconda-project-lock.yml`` layout is::

        env_specs:
          <env>:
            locked: true
            platforms: [linux-64, osx-64, ...]
            packages:
              all:   [...]       # every platform
              unix:  [...]       # linux-* and osx-*
              win-64: [...]      # platform-specific
              linux-64: [...]
              ...

    We return ``all`` ∪ (``unix`` if any unix platform is in scope) ∪
    per-platform entries for platforms declared by the env spec. Falling back
    to every platform group present if the env doesn't declare platforms.
    """
    entry = (lock_data.get("env_specs") or {}).get(env_name) or {}
    if not entry:
        return []
    if entry.get("locked") is False:
        return []

    buckets = entry.get("packages") or {}
    platforms = list(entry.get("platforms") or spec_platforms or [])

    want = {"all"}
    if platforms:
        want.update(platforms)
        if any(p.startswith(("linux-", "osx-")) for p in platforms):
            want.add("unix")
    else:
        want.update(buckets.keys())

    out: list[str] = []
    for group in buckets:
        if group in want:
            for pkg in buckets[group] or []:
                if pkg not in out:
                    out.append(pkg)
    return out


def _command_shell(cspec, command_kinds: dict, cname: str) -> str | None:
    """Best-effort shell string for a command spec.

    Follows the conventions used by ``anaconda-project export-pixi``:
    notebook commands become ``jupyter notebook <path>`` and bokeh_app
    commands become ``bokeh serve <path>``. The original kind + path is
    recorded in *command_kinds* so no fidelity is lost.
    """
    if isinstance(cspec, str):
        return cspec
    if not isinstance(cspec, dict):
        return None
    for key in ("unix", "bash"):
        if cspec.get(key):
            return cspec[key]
    if cspec.get("notebook"):
        command_kinds.setdefault(cname, {})["notebook"] = cspec["notebook"]
        return f"jupyter notebook {cspec['notebook']}"
    if cspec.get("bokeh_app"):
        command_kinds.setdefault(cname, {})["bokeh_app"] = cspec["bokeh_app"]
        return f"bokeh serve {cspec['bokeh_app']}"
    if cspec.get("windows"):
        command_kinds.setdefault(cname, {})["windows_only"] = True
        return cspec["windows"]
    return None


def _variables_content(raw_vars, proj):
    """Reduce ``variables:`` (list or dict form) to ``EnvironmentVariables``.

    The dict form's ``default`` becomes the value; prompting/encryption
    metadata is discarded for now (see upstream issue).
    """
    from projspec.content.env_var import EnvironmentVariables

    if not raw_vars:
        return None
    out: dict[str, str | None] = {}
    if isinstance(raw_vars, list):
        for name in raw_vars:
            if isinstance(name, str):
                out[name] = None
    elif isinstance(raw_vars, dict):
        for name, spec in raw_vars.items():
            if isinstance(spec, dict):
                default = spec.get("default")
                out[name] = str(default) if default is not None else None
            elif spec is None:
                out[name] = None
            else:
                out[name] = str(spec)
    if not out:
        return None
    return EnvironmentVariables(proj=proj, variables=out)


def _collect_extras(meta: dict, *, command_kinds, command_env_specs,
                    command_http, lock_enabled) -> dict:
    """Collect fields projspec does not yet model into a flat metadata dict."""
    extras: dict = {}
    for key in ("name", "description", "icon", "categories",
                "platforms", "downloads", "services", "skip_imports"):
        if key in meta and meta[key] not in (None, [], {}):
            extras[key] = meta[key]
    if command_kinds:
        extras["command_kinds"] = command_kinds
    if command_env_specs:
        extras["command_env_specs"] = command_env_specs
    if command_http:
        extras["command_supports_http_options"] = command_http
    if lock_enabled is not None:
        extras["locking_enabled"] = lock_enabled
    return extras
