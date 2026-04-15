# CODEGEN.md — projspec-rs generation guide

This document records exactly how `projspec-rs` was produced from the Python
reference implementation, and all decisions made along the way.  It is the
primary input for the next regeneration: read this before touching any code.

---

## Purpose and scope

`projspec-rs` is a Rust re-implementation of the `projspec` Python package and
CLI.  The Python version remains the **reference implementation** — it is
never modified to accommodate the Rust port.  This directory is regenerated
from scratch every time the Python source changes significantly.

Scope:
- All `ProjectSpec` matchers and parsers (40+ types)
- All `BaseContent` and `BaseArtifact` types
- All three enums (`Stack`, `Precision`, `Architecture`)
- Artifact execution (`make`, `clean`, `state`)
- `Project` struct + `resolve()` logic + child walking
- `ProjectLibrary` (JSON persistence)
- Config file (`~/.config/projspec/projspec.json`)
- Project scaffolding (`create`)
- CLI (`scan`, `make`, `create`, `info`, `version`, `library`, `config`)

Out of scope (same as AGENTS.md):
- `vsextension/`, `pycharm_plugin/`, `src/projspec/qtapp/`
- HTML output (`html.py`, `data_html.py`)
- Remote filesystem support (fsspec S3/GCS/HTTP) — Rust version is local-only

---

## How to regenerate

### Prerequisites

```bash
# Install Rust (only needed once per machine)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
```

### Steps

1. **Read AGENTS.md** in the repo root. It describes the Python architecture
   that this Rust code mirrors.  Pay particular attention to:
   - The three class families (Project, ProjectSpec, BaseContent/BaseArtifact)
   - The `parse()` contract
   - The grouping convention in `_contents` / `_artifacts`

2. **Read all Python source files** (in order):
   ```
   src/projspec/__init__.py
   src/projspec/proj/__init__.py      # list of all concrete spec classes
   src/projspec/proj/base.py          # Project, ProjectSpec, ProjectExtra
   src/projspec/proj/*.py             # every concrete spec
   src/projspec/content/__init__.py
   src/projspec/content/*.py
   src/projspec/artifact/__init__.py
   src/projspec/artifact/*.py
   src/projspec/__main__.py           # CLI commands
   src/projspec/library.py
   src/projspec/config.py
   src/projspec/tools.py
   ```

3. **Re-create the Rust source files** following the module layout below.
   Use this CODEGEN.md (especially the Decisions section) to avoid repeating
   solved problems.

4. **Compile and test**:
   ```bash
   cd projspec-rs
   cargo build
   ./target/debug/projspec scan /data
   ./target/debug/projspec scan /data --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d['specs'].keys()))"
   ./target/debug/projspec scan /data --walk --summary
   ```

---

## Module layout

```
projspec-rs/src/
  main.rs        Module declarations + fn main() → cli::run()
  types.rs       Stack, Precision, Architecture enums
  content.rs     Content enum (one variant per BaseContent subclass)
  artifact.rs    Artifact enum + MakeResult + FileArtifact / Process / etc.
  spec.rs        ParseCtx, SpecResult, all_parsers() + one fn per spec
  project.rs     Project struct, resolve(), to_json(), from_json()
  library.rs     ProjectLibrary (load/save/add/delete/filter)
  config.rs      Config (load/save/get/set/unset/defaults_table)
  create.rs      CreateSpec, all_creators() + one fn per spec type
  cli.rs         clap CLI; dispatches to the above modules
```

---

## Key design decisions

### D1: Flat enum for Content and Artifact, not trait objects

**Decision**: `Content` and `Artifact` are each a single Rust enum with one
variant per concrete Python subclass.  No `Box<dyn Trait>` or trait objects.

**Rationale**: Trait objects would require `dyn` + boxing everywhere and make
JSON serialisation harder.  Enums are exhaustive-matchable, `Clone`able, and
`Serialize`/`Deserialize`-able trivially.

**Consequence**: Every time a new Python subclass is added, a new variant must
be added to the enum.  This is intentional — the compiler enforces
completeness.

### D2: SpecResult + ParseCtx pattern instead of struct per spec

**Decision**: Each spec is a free function `parse_<name>(ctx: &ParseCtx) -> Option<SpecResult>`.
There is no per-spec struct.

**Rationale**: The Python `ProjectSpec` subclass pattern (class + `match()` +
`parse()` methods) does not map naturally to Rust without trait objects.
A function that returns `Option<SpecResult>` captures the same semantics:
`None` = `match()` returned False, `Some(r)` = successfully parsed.

`ParseCtx` is a borrow of everything a parser needs: `url`, `basenames`,
`pyproject`.  Parsers call `ctx.read_text()`, `ctx.read_toml()`,
`ctx.read_yaml()` — the same operations as Python's `self.proj.get_file()`.

### D3: `all_parsers()` returns a Vec of `(name, fn)` pairs

**Decision**: Registration is a static `Vec` returned by `all_parsers()`.

**Rationale**: Python uses `__init_subclass__` auto-registration into a
module-level dict.  Rust has no equivalent runtime mechanism.  A static Vec
is simple, ordered, and trivially iterable.  Order matters: more-specific
specs (e.g. `RattlerRecipe` before `CondaRecipe`, `Uv`/`Poetry` before
`PythonLibrary`) must be listed first.

**Important for regeneration**: When Python adds a new spec class, add a
corresponding `parse_*` function in `spec.rs` and an entry in `all_parsers()`.
Check the Python `proj/__init__.py` import order — that determines priority.

### D4: ProjectExtra specs are identified by `is_extra = true` in SpecResult

**Decision**: `SpecResult.is_extra` mirrors Python's `ProjectExtra`.  The
`resolve()` loop merges extras into `proj.contents`/`proj.artifacts` rather
than storing them in `proj.specs`.

### D5: TOML → JSON conversion via `toml_to_json()`

**Decision**: `pyproject.toml` is parsed with the `toml` crate, then converted
to `serde_json::Value` via a recursive `toml_to_json()` helper.

**Rationale**: All parsers use `serde_json::Value` as the common interchange
type.  This avoids having both `toml::Value` and `serde_json::Value` in scope.
The conversion is lossless for all types relevant to pyproject.toml.

### D6: Jinja stripping for conda YAML files

**Decision**: `strip_jinja()` removes lines containing `{%…%}` and strips
selector comments like `# [linux]`.  Template variables (`{{…}}`) are left
as-is if jinja2-style rendering would be needed.

**Rationale**: The Python reference uses `_yaml_no_jinja()` with similar logic.
The Rust version is simpler — it does not attempt to evaluate Jinja templates,
it only removes control-flow lines so the YAML is parseable.

**Consequence**: Recipes that heavily use Jinja2 set-expressions will parse
with placeholder strings instead of resolved values.  This is acceptable for
introspection purposes.

### D7: to_json() is custom, from_json() is partial

**Decision**: `Project::to_json()` builds a `serde_json::Value` manually
rather than using `serde::Serialize` on the struct.

**Rationale**: The `Content` and `Artifact` enums use `#[serde(tag = ...)]`
which requires a `klass_name` field that is not present in the struct.
Using `serde_json::to_value()` directly on the top-level `Project` produces
`{}` due to the internally-tagged enum issue.  The manual approach is explicit
and produces a clean, predictable JSON shape.

`from_json()` only reconstructs `path`, `url`, `specs` (name + spec_doc only),
and `children` — enough for library listing and filtering.
Contents/artifacts are not round-tripped from JSON at this time; they are
re-parsed on demand by calling `Project::new()`.

### D8: serde_yaml for YAML parsing

**Decision**: `serde_yaml` crate (0.9) is used for all YAML files.

**Rationale**: Simple API, parses to `serde_json::Value`-compatible structures.
Note: `serde_yaml 0.9` is marked deprecated by its author in favour of
`libyaml-safer`, but remains widely used and stable.  Consider migrating to
`serde_yml` (the community fork) on next regeneration if needed.

### D9: Artifact execution model

**Decision**: `Artifact::make(cwd, wait)` returns `MakeResult`.

- `FileArtifact::make()` runs the command, then globs for produced files →
  `MakeResult::FilesProduced`.
- `Process::make(wait=true)` runs to completion → `MakeResult::Completed`.
- `Process::make(wait=false)` spawns and forgets (server mode) →
  `MakeResult::ProcessSpawned { pid }`.
- `HelmDeployment::make()` → `MakeResult::Deployed`.

**Rationale**: The Python version stores a live `subprocess.Popen` handle on
the artifact instance.  Rust cannot do this without unsafe lifetime tricks.
Instead, the CLI prints the PID and exits; the user manages the server process
externally.  For batch processes, `wait=true` is the default.

### D10: Library persistence is local-only

**Decision**: `ProjectLibrary` reads/writes a local JSON file only.  No fsspec
remote support.

**Rationale**: The Python version uses `fsspec.open()` which transparently
supports S3/GCS/etc.  The Rust version uses `std::fs` only.  Remote library
paths are listed as a future enhancement.

### D11: `scan_max_size` and content scanning

**Decision**: The Rust version does **not** implement content scanning
(reading file bytes to detect Marimo, Flask, etc.).  Instead, `parse_marimo()`
reads `.py` files directly from disk.

**Rationale**: The Python version's `scanned_files` dict pre-reads small files
for all spec parsers to share.  In Rust, each parser reads what it needs.
The `scan_max_size` config is preserved for compatibility but not enforced
(all files are read on demand).

---

## What changed from Python → Rust

| Python | Rust |
|---|---|
| `__init_subclass__` auto-registration | Static `all_parsers()` Vec |
| `ProjectSpec` class per spec type | Free function `parse_<name>()` |
| `AttrDict` | `HashMap<String, Content/Artifact>` |
| `ProjectExtra` subclass | `SpecResult { is_extra: true }` |
| `fsspec` remote FS | Local `std::fs` only |
| `scanned_files` pre-read cache | On-demand file reads per parser |
| `to_dict(compact=False)` round-trip | Partial: `to_json()` + `from_json()` |
| HTML output | Not implemented |
| `Project.make(qname)` | `Project::find_artifact(qname)` + `art.make()` |
| `pydoc.doc(cls)` in `info` command | JSON class listing |

---

## Known gaps / future work

1. **Content/artifact round-trip from JSON** — `from_json()` currently drops
   contents and artifacts when loading from library.  The JSON is saved
   correctly; add `Content`/`Artifact` deserialisers to restore fully.

2. **Remote filesystem** — Add optional S3/GCS support (e.g. via `object_store`
   crate) to match Python's fsspec usage.

3. **UvScript spec** — Inline `# /// script` metadata in `.py` files requires
   content scanning.  Currently not implemented; add it alongside D11 fix.

4. **Django app detection** — Full detection requires walking `*/settings.py` +
   `*/urls.py`.  Current implementation matches `manage.py` but does not find
   app directories.

5. **Pixi lock file parsing** — The Rust version reads lock-file presence but
   does not parse individual environment packages from `pixi.lock` (YAML).
   Add this to get full environment content from locked pixi projects.

6. **`briefcase` multi-app / platform support** — Python version iterates all
   apps × platforms.  Rust version only adds a linux-deb artifact as a stub.

7. **`serde_yaml` migration** — When the `serde_yaml` 0.9 deprecation becomes
   a practical issue, migrate to `serde_yml` (drop-in fork).

---

## Regeneration checklist

When the Python reference changes, run through this list:

- [ ] Re-read `src/projspec/proj/__init__.py` — were new spec classes added?
      Add corresponding `parse_*` functions in `spec.rs` and entries in
      `all_parsers()`.
- [ ] Re-read changed `proj/*.py` files — did `match()` criteria change?
      Update the corresponding `parse_*` function.
- [ ] Re-read `content/*.py` — were new content fields or classes added?
      Update `Content` enum variants and their `summary()` arms.
- [ ] Re-read `artifact/*.py` — were new artifact types added?
      Update `Artifact` enum and execution logic.
- [ ] Re-read `__main__.py` — were new CLI commands or options added?
      Update `cli.rs`.
- [ ] Re-read `config.py` — were new config keys added?
      Update `Config` struct and `defaults_table()`.
- [ ] Compile: `cargo build`
- [ ] Smoke-test: `./target/debug/projspec scan /data` and compare output
      with Python: `python -m projspec scan /data`
- [ ] Update this CODEGEN.md with any new decisions made.
