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
| `fsspec` remote FS | `opendal::blocking::Operator` via `Vfs` struct in `fs.rs` |
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

2. **Remote filesystem** — Implemented via `opendal` (see D-FS1–D-FS5 below).
   S3 (including moto/minio), HTTP, local Fs, and memory backends are supported.
   GCS / Azure / HDFS are available via opendal features but not yet wired up in
   `vfs_from_url()`.

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
- [ ] **Prefetch maintenance** (see D-PF4):
      - New `ctx.vfs_exists("sub/path")` in spec.rs? → add to `subpaths_to_prefetch()`.
      - New parser reads a file with an extension not in `PREFETCH_EXTS`? → add extension.
      - New `ctx.read_text("name.yaml")` etc.? → no action needed (covered by extension rule).
- [ ] Compile: `cargo build`
- [ ] Run tests: `cargo test --test test_memory && cargo test --test test_http && cargo test --test test_s3 -- --test-threads=1`
- [ ] Smoke-test: `./target/debug/projspec scan /data` and compare output
      with Python: `python -m projspec scan /data`
- [ ] Update this CODEGEN.md with any new decisions made.

---

## Remote filesystem with opendal (D-FS1 – D-FS5)

Added in the second iteration of projspec-rs.

### D-FS1: `opendal::blocking::Operator` — not async

opendal's primary API is async (tokio-based).  The parsers are CPU-bound string
processing and are synchronous throughout.  We use `opendal::blocking::Operator`
which internally calls `block_on()` on a tokio runtime.  A single global
`tokio::runtime::Runtime` is created via `OnceLock` in `fs.rs:get_runtime()` and
reused for every Vfs operation.

**Decision**: one global runtime, not per-request.  Multiple `Vfs` instances
share the same runtime; this is safe because `blocking::Operator` is `Clone`.

### D-FS2: `Vfs` is a struct, not a trait

`Vfs` wraps `opendal::blocking::Operator` directly.  No `dyn Vfs` boxing.
`ParseCtx` holds `&'a Vfs` (a borrow), so it is zero-cost.  If multiple
heterogeneous backends per parse-pass are ever needed, introduce a trait then.

### D-FS3: Operator root = project root; paths are relative

Each `Vfs` is rooted at the project directory (or bucket prefix for S3).
All file reads inside parsers use relative paths (e.g. `"pyproject.toml"`,
not `"/data/pyproject.toml"`).  `vfs.basenames()` returns `{basename: basename}`
(the relative path equals the basename at the root level).

**For S3**: `list_dir("/")` returns object keys relative to the configured root
prefix.  No path translation is needed.

**For HTTP**: `list_dir()` is not supported (opendal Http only provides read+stat).
The `parse_http()` helper in the HTTP test manually constructs the basenames map.
In production `Project::new_with_vfs()` with an HTTP backend will produce an
empty project unless basenames are supplied externally (e.g. from a manifest).

### D-FS4: HTTP backend limitation — no listing

The opendal `services::Http` builder supports `read` and `stat` only.
`list_dir()` returns an empty vec for HTTP backends.

**Consequence**: `Project::new_with_vfs()` produces an empty project when called
with an HTTP `Vfs` and no externally-provided basenames, because `vfs.basenames()`
returns `{}`.

**Workaround implemented in tests**: `parse_http()` in `tests/test_http.rs`
manually builds the basenames from a known list of filenames, then constructs
a `ParseCtx` directly.

**Future work**: add a `basenames_override` parameter to `Project::new_with_vfs()`
so callers can supply a pre-populated basenames map (e.g. from an index file or
directory manifest).

### D-FS5: S3 credentials from environment variables only

The opendal S3 builder automatically loads credentials from environment:
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_ENDPOINT_URL`.
We do **not** call `disable_config_load()` so the full AWS credential chain works.

For moto (test S3), these env vars are set to dummy values before each test.
The `set_moto_env()` helper uses `unsafe { std::env::set_var(...) }` because
`set_var` is unsafe in Rust 2024; tests run with `--test-threads=1` to avoid
data races on env vars.

`AWS_ENDPOINT_URL` is the standard env var for pointing S3 clients at a custom
endpoint (moto, minio, etc.).  opendal reads it via its `disable_config_load`
flag being absent.

### D-FS6: `lib.rs` added for integration tests

Because this crate is a `[[bin]]`-only crate, integration tests in `tests/`
cannot import internal modules.  Adding `[lib]` with `name = "projspec_rs"` and
a `src/lib.rs` that re-exports all modules allows tests to use `projspec_rs::fs`,
`projspec_rs::project`, etc.

The binary (`main.rs`) continues to declare its own `mod` statements and call
`cli::run()`; the library crate independently exposes the same modules.

### D-FS7: moto server startup protocol

The Python moto fixture (`tests/fixtures/moto_server.py`):
1. Starts a werkzeug HTTP server on port 0 (OS-assigned).
2. Populates a `projspec-test` bucket with fixture files.
3. **Prints the actual port on stdout** (single line, flushed).
4. Blocks on `sys.stdin.read()` until stdin closes (Rust drops the child's stdin pipe).

The Rust test reads the first stdout line to get the port.  werkzeug request
logs are suppressed (`logging.getLogger("werkzeug").setLevel(ERROR)`) to prevent
them from appearing before the port line.

### Testing commands

```bash
# Fast: no external processes
cargo test --test test_memory

# Requires Python + http.server stdlib (built-in)
cargo test --test test_http

# Requires: pip install moto[server] boto3 flask-cors
# Run single-threaded to avoid env-var races
cargo test --test test_s3 -- --test-threads=1

# All tests
cargo test --test test_memory && \
cargo test --test test_http && \
cargo test --test test_s3 -- --test-threads=1
```

---

## Concurrent file prefetch (D-PF1 – D-PF4)

Added in the third iteration of projspec-rs.

### Motivation

Each call to `ctx.read_text()` / `ctx.read_yaml()` / `ctx.read_toml()` inside a
parser is a synchronous VFS operation.  For local `Fs` this costs microseconds.
For HTTP and S3 each call is a network round-trip (1–100 ms).  With ~25 files
potentially read across all parsers, sequential access adds up to seconds on
remote backends.

### D-PF1: Pre-fetch all candidate files in parallel before parsers run

In `project.rs::resolve()`, after `vfs.basenames()` returns and `pyproject.toml`
is parsed, two parallel operations are launched via `rayon::par_iter`:

1. **File reads** — `files_to_prefetch()` returns the static list of all
   filenames any parser might read, intersected with the files actually present
   in `basenames`.  Each present file is read once concurrently.  Result:
   `file_cache: HashMap<String, String>`.

2. **Existence checks** — `subpaths_to_prefetch()` returns sub-paths below the
   root that parsers check via `ctx.vfs_exists()` (e.g. `.vscode/settings.json`,
   `.idea`).  Each is stat'd concurrently.  Result:
   `exists_cache: HashMap<String, bool>`.

Both caches are owned by `resolve()` and passed into `ParseCtx` as borrows.

### D-PF2: `pyproject.toml` is read before prefetch, not during it

`pyproject.toml` must be read before `files_to_prefetch()` is called because
future enhancements might use its contents to decide which additional files to
include (e.g. if `[tool.pixi]` is present, include `pixi.lock`).  It is
therefore excluded from the static prefetch list to avoid double-reading.

### D-PF3: `ParseCtx` cache check order

`ParseCtx::read_text(name)` now:
1. Checks `file_cache` (HashMap lookup, O(1), zero I/O).
2. On miss: looks up `rel = basenames[name]`, then calls `vfs.read_text(rel)`.

`ParseCtx::vfs_exists(path)` now:
1. Checks `exists_cache`.
2. On miss: calls `vfs.exists(path)` live.

`parse_marimo` — the only content-scanning parser — calls `ctx.read_text_path(rel)`
which also checks `file_cache` keyed by the relative path.  Since `.py` files are
included in the dynamic part of `files_to_prefetch()`, marimo scanning is always
cache-served after the first project instantiation.

### D-PF4: Maintenance rules — what requires manual upkeep

**File contents (`files_to_prefetch`)** — **no manual upkeep required** for
new parsers, provided they read files of a recognised type.  The function
prefetches every file in `basenames` whose extension (or name) matches a fixed
set of metadata formats:

| Extension / name | Examples |
|---|---|
| `.toml` | pixi.toml, Cargo.toml, book.toml, pyscript.toml |
| `.yaml` / `.yml` | Chart.yaml, .readthedocs.yaml, environment.yml |
| `.json` | package.json, datapackage.json, .zenodo.json |
| `.txt` | requirements.txt, LICENSE.txt |
| `.md` | README.md, CITATION.md |
| `.lock` | uv.lock, poetry.lock, pixi.lock |
| `.cff` | CITATION.cff |
| `.py` | marimo content-scan, pyscript |
| `.mod` | go.mod |
| `MLFlow`, `Dockerfile` | exact-name match |
| `LICENSE*`, `LICENCE*`, `COPYING*` | prefix match |

`pyproject.toml` is always excluded — it is read before prefetch.

If a future parser reads a file with an extension **not** in this list (e.g.
`.rb`, `.gradle`), add that extension to `PREFETCH_EXTS` in
`project.rs::files_to_prefetch()`.  That is the only maintenance needed.

**File listing (`basenames`)** — **no upkeep needed at all**.  `basenames` is
built by a single `vfs.basenames()` call at the start of `resolve()` and is
available to all parsers as a free HashMap lookup via `ctx.has()` /
`ctx.has_any()`.  It already covers the full root listing.

**Sub-path existence (`subpaths_to_prefetch`)** — **manual upkeep required**.
These are paths *inside* sub-directories (e.g. `.vscode/settings.json`) that
cannot be inferred from the root listing.  Add an entry here whenever a new
`ctx.vfs_exists("some/sub/path")` call is introduced in spec.rs.

### Performance impact

| Backend | Before | After |
|---|---|---|
| Local `Fs` | ~0.5 ms (25 sequential syscalls) | ~0.1 ms (parallel, OS cache) |
| Memory | ~0 ms | ~0 ms (no change) |
| HTTP (100 ms RTT) | ~2.5 s (25 × 100 ms) | ~100 ms (parallel) |
| S3 (20 ms RTT) | ~500 ms (25 × 20 ms) | ~20 ms (parallel) |

Actual numbers depend on backend latency, connection pool size, and how many
files are actually present.  For a minimal Python project (pyproject.toml + uv.lock
+ README.md) the effective file count is ~3, so the improvement is ~3× even
without parallelism.
