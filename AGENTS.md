# AGENTS.md — projspec

This document is a guide for AI coding agents working in this repository. It
covers the architecture of the `projspec` package (located in `src/projspec/`),
the three central class families, the contract every `parse()` method must
honour, and the conventions used throughout.

Extensions and the Qt application (`vsextension/`, `pycharm_plugin/`,
`src/projspec/qtapp/`) are out of scope. See `vsextension/ACTIONS.md` for
the VSCode extension specification.

---

## Repository layout

```
src/projspec/
  __init__.py          # public re-exports: Project, ProjectSpec, get_cls
  proj/
    base.py            # Project, ProjectSpec, ProjectExtra, ParseFailed
    *.py               # one file per concrete spec type
  content/
    base.py            # BaseContent + content registry
    *.py               # one file per concrete content type
  artifact/
    base.py            # BaseArtifact, FileArtifact + artifact registry
    *.py               # one file per concrete artifact type
  utils.py             # AttrDict, camel_to_snake, run_subprocess, …
  config.py            # get_conf / set_conf
vsextension/           # a UI for vscode, calling projspec as a subprocess
qtapp/                 # standalone UI on pyqt5, calling projspec in-process
tests/
  conftest.py          # shared fixtures (proj = Project("/data"))
  test_basic.py        # smoke tests
  test_roundtrips.py   # serialise / deserialise round-trips
  …
```

---

## The three class families

### 1. `Project`  (`proj/base.py:43`)

The top-level container for a parsed directory.  It is not subclassed.

Key attributes set during `__init__` → `resolve()`:

| attribute | type | description |
|-----------|------|-------------|
| `specs` | `AttrDict` | matched `ProjectSpec` instances, keyed by snake-case class name |
| `contents` | `AttrDict` | `BaseContent` instances contributed by `ProjectExtra` specs |
| `artifacts` | `AttrDict` | `BaseArtifact` instances contributed by `ProjectExtra` specs |
| `children` | `AttrDict` | child `Project` instances found by directory walking |
| `fs` | `fsspec.AbstractFileSystem` | filesystem used for all file I/O |
| `url` | `str` | FS-normalised path to the project root |
| `basenames` | `dict[str, str]` | `{basename: full_path}` for every entry at the root |
| `pyproject` | `dict` | parsed `pyproject.toml`, or `{}` |

`Project.resolve()` iterates every registered `ProjectSpec` subclass and calls
`cls(proj)` (which runs `match()`) then `inst.parse()`.  A `ValueError` /
`ParseFailed` means the directory did not match that type and is silently
skipped.  Any other exception is logged but does not abort parsing.

`ProjectExtra` subclasses are handled differently: their `contents` and
`artifacts` are merged directly into `proj.contents` / `proj.artifacts` rather
than being stored in `proj.specs`.

---

### 2. `ProjectSpec`  (`proj/base.py:435`)

Base class for every concrete project type.  Subclasses are **auto-registered**
on import via `__init_subclass__` using their snake-case name as the key
(`proj/base.py:511`).

Lifecycle inside `Project.resolve()`:

```
cls(proj)          ← __init__ calls self.match(); raises ParseFailed if False
inst.parse()       ← populate self._contents and self._artifacts
```

Important class-level attribute:

| attribute | description |
|-----------|-------------|
| `spec_doc` | URL to upstream specification docs (optional but encouraged) |

Instance attributes after `parse()`:

| attribute | type | description |
|-----------|------|-------------|
| `_contents` | `AttrDict` | content objects for this spec |
| `_artifacts` | `AttrDict` | artifact objects for this spec |
| `proj` | `Project` | back-reference to the owning project |

Public properties `.contents` and `.artifacts` delegate to `_contents` /
`_artifacts` and call `parse()` lazily if they are `None` (`proj/base.py:466`).

#### `ProjectExtra`  (`proj/base.py:542`)

A special subclass of `ProjectSpec` for cross-cutting concerns (CI/CD, Docker,
pre-commit, requirements files, …).  These specs are *not* standalone projects.
After parsing, `Project.resolve()` merges their `contents` / `artifacts` into
the root project rather than storing them in `proj.specs`.

---

### 3. `BaseContent`  (`content/base.py:11`)

A **dataclass** holding descriptive information extracted from a project.
Content objects are read-only descriptions; they have no executable behaviour.

Every subclass is a `@dataclass` that **must** include `proj: Project` as its
first field (inherited from `BaseContent`).

Subclasses are auto-registered on import via `__init_subclass__` (keyed by
snake-case name).

Concrete content classes:

| class | module | fields |
|-------|--------|--------|
| `Environment` | `content/environment.py` | `stack: Stack`, `precision: Precision`, `packages: list[str]`, `channels: list[str]` |
| `Command` | `content/executable.py` | `cmd: list[str] \| str` |
| `DescriptiveMetadata` | `content/metadata.py` | `meta: dict[str, str]` |
| `License` | `content/metadata.py` | `shortname`, `fullname`, `url` |
| `PythonPackage` | `content/package.py` | `package_name: str` |
| `RustModule` | `content/package.py` | `name: str` |
| `NodePackage` | `content/package.py` | `name: str` |
| `FrictionlessData` | `content/data.py` | `name: str`, `schema: dict` |
| `IntakeSource` | `content/data.py` | `name: str` |
| `EnvironmentVariables` | `content/env_var.py` | `variables: dict[str, str \| None]` |

Helper enums used by `Environment`:

- `Stack` (`PIP`, `CONDA`, `NPM`) — packaging technology
- `Precision` (`SPEC`, `LOCK`) — how precisely the environment is pinned

---

### 4. `BaseArtifact`  (`artifact/base.py:14`)

An executable action or producible output attached to a project.

Constructor signature: `__init__(self, proj: Project, cmd: list[str] | None, **kwargs)`

All extra keyword arguments are stored via `self.__dict__.update(kwargs)`.

Key interface:

| method | description |
|--------|-------------|
| `make(**kwargs)` | Execute/produce the artifact. Raises `RuntimeError` for remote projects. |
| `clean()` | Remove or stop the artifact. Default no-op. |
| `remake()` | `clean()` then `make()`. |
| `state` | Property returning `"clean"`, `"done"`, `"pending"`, or `""`. |

Subclasses are auto-registered on import via `__init_subclass__`.

`FileArtifact` (`artifact/base.py:108`) specialises `BaseArtifact` for outputs
that are one or more files.  Constructor adds `fn: str` (glob pattern for
output path).  `_is_done()` / `_is_clean()` check for the file's existence via
`proj.fs.glob(self.fn)`.

Concrete artifact classes:

| class | module | description |
|-------|--------|-------------|
| `Process` | `artifact/process.py` | Subprocess / long-running service |
| `Server` | `artifact/process.py` | HTTP service (subclass of `Process`) |
| `Wheel` | `artifact/installable.py` | Python wheel (`dist/*.whl`) |
| `CondaPackage` | `artifact/installable.py` | Conda `.conda` package |
| `SystemInstallablePackage` | `artifact/installable.py` | OS installer (deb, msi, dmg, …) |
| `VirtualEnv` | `artifact/python_env.py` | Python venv directory |
| `CondaEnv` | `artifact/python_env.py` | Conda environment directory |
| `LockFile` | `artifact/python_env.py` | Lock-file on disk |
| `EnvPack` | `artifact/python_env.py` | Packed environment archive |
| `DockerImage` | `artifact/container.py` | Docker image |
| `DockerRuntime` | `artifact/container.py` | Running Docker container |
| `PreCommit` | `artifact/linter.py` | pre-commit hook runner |

---

## Writing a `parse()` method

`parse()` is the core obligation of every `ProjectSpec` subclass.  The base
implementation simply raises `ParseFailed`, so not calling `super().parse()` is
normal.

### Contract

1. **Populate `self._contents` and `self._artifacts`** — both must be
   `AttrDict` instances (or remain empty `AttrDict()`).  They must not be
   `None` after `parse()` returns.

2. **Grouping convention** — keys inside `_contents` / `_artifacts` are
   snake-case *type names* (`"environment"`, `"wheel"`, `"process"`, …).
   If there are multiple instances of the same type, the value is itself an
   `AttrDict` keyed by an identifying name (e.g. `"default"`, `"test"`,
   `"main"`).

   ```python
   # single item
   self._contents["python_package"] = PythonPackage(proj=self.proj, package_name="foo")

   # multiple items of the same type
   self._artifacts["process"] = AttrDict(
       main=Process(proj=self.proj, cmd=["python", "__main__.py"]),
   )
   ```

3. **Every content/artifact must receive `proj=self.proj`** — this back-
   reference is required by `BaseContent` / `BaseArtifact`.

4. **Raise `ParseFailed` (or any `ValueError`) on unrecoverable bad state** —
   for example if a required file is malformed and you cannot produce
   meaningful output.  Do *not* raise for optional fields that simply aren't
   present.

5. **Read files via `self.proj.get_file(name)` or `self.proj.fs`** — never
   use plain `open()`.  This keeps parsing compatible with remote filesystems
   (S3, GCS, HTTP, …).

6. **Use `self.proj.basenames` for existence checks** — it is a
   `{basename: full_path}` dict of the top-level directory, already loaded,
   so it is cheap to query.

7. **Keep it cheap** — `match()` runs for every registered type on every
   directory; `parse()` runs immediately afterwards if `match()` returns
   `True`.  Read only the files you actually need and avoid recursive
   directory traversal.

8. **Use `self.proj.pyproject`** for any data in `pyproject.toml` — it is a
   `@cached_property` that is shared with other specs in the same resolve
   pass.

### Minimal example

```python
from projspec.proj.base import ProjectSpec, ParseFailed
from projspec.content.environment import Environment, Stack, Precision
from projspec.artifact.python_env import LockFile
from projspec.utils import AttrDict


class MyTool(ProjectSpec):
    """Projects managed by mytool (mytool.toml present)."""

    spec_doc = "https://mytool.example.com/spec"

    def match(self) -> bool:
        return "mytool.toml" in self.proj.basenames

    def parse(self) -> None:
        import toml
        from projspec.utils import PickleableTomlDecoder

        try:
            with self.proj.get_file("mytool.toml") as f:
                meta = toml.load(f, decoder=PickleableTomlDecoder())
        except (OSError, ValueError):
            raise ParseFailed("Could not read mytool.toml")

        packages = meta.get("dependencies", [])
        self._contents = AttrDict(
            environment=Environment(
                proj=self.proj,
                stack=Stack.PIP,
                precision=Precision.SPEC,
                packages=packages,
                channels=[],
            )
        )
        self._artifacts = AttrDict(
            lock_file=LockFile(
                proj=self.proj,
                cmd=["mytool", "lock"],
                fn=f"{self.proj.url}/mytool.lock",
            )
        )
```

### `ProjectExtra.parse()` — additional note

`ProjectExtra.parse()` should write to `self._contents` / `self._artifacts`
(accessed as `self.contents` / `self.artifacts` via the property) exactly as
above.  `Project.resolve()` merges these into the root project automatically.

---

## Registry and discovery

All three class families self-register via `__init_subclass__`:

```
projspec.proj.base.registry        # ProjectSpec subclasses
projspec.content.base.registry     # BaseContent subclasses
projspec.artifact.base.registry    # BaseArtifact subclasses
```

Keys are **snake-case class names** produced by `camel_to_snake(cls.__name__)`.
A new spec is discovered automatically the moment its module is imported.
All concrete specs are imported in `src/projspec/proj/__init__.py`, so adding
a new file there is all that is needed to register a new type.

`get_cls(name, registry="proj")` (`utils.py:358`) looks up any class by name
across all registries.

---

## `AttrDict` (`utils.py:50`)

A `dict` subclass that also supports attribute-style read access.

```python
d = AttrDict(foo=42)
d.foo  # → 42
d["foo"]  # → 42
```

`parse()` always assigns `AttrDict` instances to `self._contents` and
`self._artifacts`, never plain `dict`.

---

## Serialisation

Every content, artifact, and spec class implements `to_dict(compact=True)`.

- `compact=True` — human-readable condensed form (strings, nested dicts).
- `compact=False` — full form including a `"klass"` key that encodes the
  category and snake-case class name, enabling round-trip deserialisation
  via `utils.from_dict()`.

The test suite exercises round-trips in `tests/test_roundtrips.py`.

---

## Testing

```bash
pytest tests/
```

The `proj` fixture in `tests/conftest.py` returns
`projspec.Project("/data")` — the repository root itself — which is a
real `PythonLibrary` + `GitRepo` + `Pixi` project, so most tests work
against live on-disk data.

New specs should add at minimum:

1. A `match()` unit test verifying the positive and negative cases.
2. A `parse()` unit test asserting expected keys in `.contents` and
   `.artifacts`.
3. A round-trip test (`to_dict` → `from_dict`) if the spec introduces new
   content or artifact classes.
