Textual TUI for projspec
-------------------------

Terminal-based filesystem and library browser, functionally equivalent to
``qtapp`` but running entirely in the terminal via [Textual](https://textual.textualize.io/).

## Layout

```
┌────────────────┬────────────────┬──────────────────────────┐
│  Filesystem    │    Library     │         Details          │
│  (left)        │   (centre)     │         (right)          │
│                │                │                          │
│  📁 myproject  │ myproject      │ myproject                │
│  📁 other      │   python_lib   │   python_library         │
│  📄 README.md  │   git_repo     │     packages: [...]      │
│                │   • wheel Make │   git_repo               │
│                │                │     branch: main         │
└────────────────┴────────────────┴──────────────────────────┘
```

- **Left** — filesystem tree.  Selecting a directory parses it with projspec
  and adds it to the library if any specs are matched.
- **Centre** — library panel showing all known projects with their specs,
  contents, and artifacts.  Selecting an artifact node triggers `make`.
- **Right** — full detail tree for the selected project.

## Key bindings

| Key | Action |
|-----|--------|
| `h` | Go to home directory |
| `u` | Go up one directory level |
| `g` | Go to an arbitrary path (opens dialog) |
| `s` | Scan the current directory (walk=True, adds all sub-projects) |
| `c` | Create a new project type in the current directory (opens dialog) |
| `q` / `Ctrl+C` | Quit |

## Running

```bash
python textapp/main.py [path]
```

Or, after installing the package with the `textual` extra:

```bash
pip install "projspec[textual]"
projspec-tui [path]
```
