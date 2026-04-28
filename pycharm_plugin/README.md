# projspec PyCharm Plugin

PyCharm integration for the [projspec](https://github.com/fsspec/projspec) CLI tool.

<!-- Plugin description -->
PyCharm integration for the **projspec** CLI tool.

- Browse your **Project Library** in a dedicated sidebar tool window
- **Add**, **Rescan** and **Remove** directories from the library
- **Create** new spec types inside an existing project with autocomplete
- **Make** individual artifacts in an interactive terminal tab
- Open projects with VSCode, PyCharm, Jupyter Lab, or the system file browser
- Edit the projspec configuration file with one click

Requires the `projspec` CLI. Configure the binary path under
**Settings → Tools → Projspec**.
<!-- Plugin description end -->

## Installation

1. Install the plugin from JetBrains Marketplace (search for `projspec`), or
   build from source with `./gradlew buildPlugin`.
2. Open **Settings → Tools → Projspec** and set the path to your `projspec` binary
   (or leave as `projspec` if it is on your `PATH`).
3. The **Project Library** tool window appears in the left sidebar.

## UI overview

The tool window has two panes, mirroring the VSCode extension described in
[`vsextension/ACTIONS.md`](../vsextension/ACTIONS.md):

- **Library (left)** – a toolbar (*Add*, *Reload*, *Configure*), a filter
  field, and one widget per registered project.  Each widget shows the
  project's basename, URL, storage options, and colour-coded chips for its
  *Contents*, *Artifacts* and spec types.  A kebab menu offers *Open with
  VSCode / system filebrowser / PyCharm / jupyter*, *Rescan*, *Create spec*
  and *Remove from library*.
- **Details (right)** – title, doc/link for the selected spec, and one
  card per content/artifact of the selected project.  Artifact cards
  include a **Make** button (runs `projspec make …` in a terminal tab) and
  every card has an **ℹ️** info popup.  Bodies render as a YAML-style
  collapsible tree, with enum values shown by their member name.

## Development

### Prerequisites

- JDK 21
- Gradle 9.x (the Gradle Wrapper is included)

### Run configurations

After opening the project in IntelliJ IDEA, three pre-configured run configurations
are available from the `.run/` directory:

| Configuration | Gradle task | Description |
|---|---|---|
| **Run Plugin** | `runIde` | Launch a sandboxed PyCharm instance with the plugin loaded. Use the Debug icon for breakpoint debugging. |
| **Run Tests** | `check` | Run all unit tests and generate a Kover coverage report. |
| **Run Verifications** | `verifyPlugin` | Run the IntelliJ Plugin Verifier to check compatibility against the target IDE range. |

### Build

```bash
./gradlew buildPlugin          # produces build/distributions/projspec-pycharm-*.zip
./gradlew runIde               # launch sandboxed PyCharm
./gradlew check                # run tests + coverage
./gradlew verifyPlugin         # plugin compatibility check
./gradlew publishPlugin        # publish to JetBrains Marketplace (requires secrets)
```

### Environment variables (for signing & publishing)

| Variable | Purpose |
|---|---|
| `PRIVATE_KEY` | RSA private key for plugin signing |
| `PRIVATE_KEY_PASSWORD` | Password for the private key |
| `CERTIFICATE_CHAIN` | Certificate chain for plugin signing |
| `PUBLISH_TOKEN` | JetBrains Marketplace publish token |

## Architecture

This plugin is a Kotlin port of the VSCode `projspec` extension
(`vsextension/`).  The HTML/CSS/JavaScript that draws the two-pane UI is
**reused verbatim** from the VSCode webview – the only changes needed for
JCEF are:

1. `acquireVsCodeApi().postMessage(msg)` → `window.__javaBridge.query(JSON.stringify(msg))`
   (the bridge is a `JBCefJSQuery` registered from Kotlin).
2. `panel.webview.postMessage(msg)` → `window.__projspecDeliver(msg)`
   (Kotlin calls this via `executeJavaScript` because JCEF does not deliver
   host→frame `message` events the way VSCode does).
3. A `:root { --vscode-*: … }` block is prepended to the stylesheet so the
   VSCode theme variables map to Darcula-ish colours.

Key type mapping between the two implementations:

| VSCode concept                | PyCharm equivalent                                     |
|-------------------------------|--------------------------------------------------------|
| `createWebviewPanel`          | `JBCefBrowser` (JCEF/Chromium)                         |
| `acquireVsCodeApi()`          | `JBCefJSQuery` (`window.__javaBridge`)                 |
| `panel.webview.postMessage`   | `executeJavaScript("window.__projspecDeliver(…)")`     |
| `commands.registerCommand`    | Tool-window message dispatch                           |
| `showOpenDialog`              | `FileChooser.chooseFile` with a folder descriptor      |
| `workspace.openTextDocument`  | `FileEditorManager.openFile` + `LocalFileSystem`       |
| `createTerminal` / `sendText` | `TerminalToolWindowManager` (via reflection)           |
| `child_process.spawn`         | `GeneralCommandLine` + `CapturingProcessHandler`       |
| `showErrorMessage`            | Balloon notification via the `Projspec` group          |

### Source layout

```
src/main/kotlin/com/projspec/
    toolwindow/
        HtmlContent.kt                 — the full HTML/CSS/JS page (reused verbatim
                                         from vsextension/src/panel.ts)
        ProjspecToolWindowFactory.kt   — registers the tool window
        ProjspecToolWindowPanel.kt     — Kotlin side of the JS↔Java bridge,
                                         mirrors panel.ts's message handlers
    util/
        ProjspecRunner.kt              — all `projspec …` subprocess invocations
        TerminalRunner.kt              — `projspec make …` in a terminal tab
        OpenWithHelper.kt              — "Open with …" kebab-menu actions
        Notifier.kt                    — balloon notification helpers
        CliResult.kt                   — Success/Failure result type
    settings/
        ProjspecSettings.kt            — persistent cliPath setting
        ProjspecSettingsConfigurable.kt — Settings → Tools → Projspec UI
```

## License

Apache 2.0 — see [LICENSE](https://github.com/fsspec/projspec/blob/main/LICENSE).
