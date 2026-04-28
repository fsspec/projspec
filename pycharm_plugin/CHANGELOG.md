<!-- Keep a Changelog guide -> https://keepachangelog.com -->

# projspec PyCharm Plugin Changelog

## [Unreleased]

### Changed
- UI re-implemented as the two-pane Library / Details layout described in
  `vsextension/ACTIONS.md`, reusing the VSCode extension's HTML, CSS and
  JavaScript verbatim inside JCEF.
- All interactions (Add, Reload, Configure, search filter, kebab menu with
  Open-with / Rescan / Create spec / Remove from library, per-artifact Make
  and ℹ️ info popups) now flow through the same message bus as the VSCode
  panel.
- Enum values in the YAML-style item tree are rendered by their member name.

### Added
- "Configure" button that opens `$PROJSPEC_CONFIG_DIR/projspec.json`
  (creating a default if absent).
- "Open with VSCode / system filebrowser / PyCharm / jupyter" launchers.
- Reveal-in-project-view button for local file artifacts.

### Removed
- Tools → Projspec menu actions (ShowLibrary, ProjspecScan, ShowProjectJson,
  ShowInfo, ShowItemDetails) — everything is now driven from the tool window.
- Split-editor JSON viewer and HTML scan preview (replaced by the webview
  Details panel).

## [0.0.1]

### Added
- Initial project scaffold created from [IntelliJ Platform Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template)

[Unreleased]: https://github.com/fsspec/projspec/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/fsspec/projspec/commits/v0.0.1
