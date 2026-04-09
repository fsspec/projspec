# projspec VSCode Extension — User Actions

This document describes every user action available in the `projspec` VSCode
extension.

The extension activates automatically once VS Code finishes starting up
(`onStartupFinished`).

---

## Command Palette Commands

### `Show Project Library`  (`projspec.showTree`)

Opens the Project Library panel.

**Steps:**
1. Runs `projspec library list --json-out` to load the project tree.
2. Runs `projspec info` once to load documentation for all spec/content/artifact types (cached for the lifetime of the window).
3. Opens the **"Project Library"** panel.

---

### `Open Project`  (`projspec.openProject`)

Opens a project folder in a new VS Code window.
This command is invoked internally when a project node is clicked inside
the Project Library panel.

- **Local projects** (`file://` URLs): opens the folder directly with
  `vscode.openFolder`.
- **Remote GCS projects** (`gs://` URLs): shows an error — "Cannot open GCS
  buckets directly. Clone the repository locally first."
- **Other URL schemes**: shows an error — "Unsupported project URL scheme: …"

---

### `Show`  (`projspec.showJson`)

Serialises a project tree node to JSON and opens it as a read-only editor tab.
This command is invoked internally from the Project Library panel when a
spec, content, or artifact node is selected.

**Steps:**
1. Receives a tree node item.
2. JSON-stringifies the node's raw data.
3. Opens a new unsaved document with JSON syntax highlighting in the editor.

---

## Project Library Panel

The Project Library panel (`projspec.showTree`) renders a custom HTML UI
inside a Webview.  The following interactive elements are available.

### Toolbar

| Element | Action |
|---------|--------|
| **Scan** button | Scans the current workspace folder into the projspec library (`projspec scan --library <folderPath>`), then refreshes the tree. |
| **Create** button | Opens the [Create Project modal](#create-project-modal). |
| **Search input** | Live-filters the tree by project name or any visible child field. Click the **×** button or press **Escape** to clear. |
| **Expand All** button | Expands every node in the tree. |
| **Collapse All** button | Collapses every node in the tree. |

### Tree Nodes
The top-level nodes are all Projects, with a name and a project URL. The name is the final portion of the URL.
Projects contain Specs, and both Specs and Projects contain Contents and Artifacts. In the tree view,
all Artifacts are show, but only Contents that are direct
children of a Project are shown.

Nodes are colour-coded:

- **Projects** — bold, folder colour
- **Contents** — teal (`#4ec9b0`)
- **Artifacts** — orange (`#ce9178`)
- **Specs** — function symbol colour

| Element | Action |
|---------|--------|
| Click a **project** node | Selects the node (no other action). Right-click to open the context menu. |
| Right-click a **project** node | Opens a context menu with two options: **Open** opens the project folder in a new VS Code window; **Remove** runs `projspec library delete <project-URL>` and refreshes the panel. |
| Click a **spec / content / artifact** node | Opens (or updates) the **Project Details** panel in the side column, showing the project's full spec/content/artifact tree with the clicked item highlighted. |
| **▶ / ▼ arrow** on any node | Toggles the visibility of that node's children. |
| **"Make" button** on an artifact node | Runs `projspec make <qname> "<projectPath>"` in a dedicated **projspec** terminal panel. |
| **"i" info button** on a spec / content / artifact node | Shows an inline popup with the item's doc string and, when available, a link to the upstream specification documentation. Press **Escape** or click elsewhere to dismiss. |

### Create Project Modal

Opened by the **Create** button in the toolbar.

| Element | Action |
|---------|--------|
| **Type input with autocomplete** | Start typing a project spec type; suggestions appear below. Use **↑ / ↓** arrow keys or click to select a suggestion. |
| **Create** button | Runs `projspec create <projectType> <folderPath>` in the current workspace folder, then automatically scans the result into the library (`projspec scan --library <folderPath>`) and refreshes the tree. |
| **Cancel** button / **Escape** key | Dismisses the modal without creating anything. |

---

## Project Details Panel

Opened when a spec, content, or artifact node is clicked in the Library panel. A single panel is reused and updated on each click.

The panel displays a header with the project name and URL, followed by a colour-coded tree of all the project's specs, contents, and artifacts — using the same visual conventions as the Library panel.

| Element | Action |
|---------|--------|
| **▶ / ▼ arrow** on any node | Toggles the visibility of that node's children. |
| **"Make" button** on an artifact node | Runs `projspec make <qname> "<projectPath>"` in a dedicated **projspec** terminal panel. |
| **"i" info button** on a spec / content / artifact node | Shows an inline popup with the item's doc string and a link to specification documentation. Press **Escape** or click elsewhere to dismiss. |
