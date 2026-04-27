# projspec VSCode Extension

This document describes as UI frontend to ``projspec`` to be used within the VSCode
IDE, its layout, details, possible actions and subprocess calls.

We will be making use of the Project, Content, Artifact and Enum concepts from the main
``projspec`` library.

Upon start-up, calls ``projspec info``, which provides a JSON mapping from Project,
Content, This data is to be stored for the whole session.
Artifact and Enum classes to records with "doc", "link" and "create"
fields, of which only "doc" is required.

## Layout

A single HTML view is exposed by the extension. This contains two principle elements:
the Project Library (left), and a Details panel (right).

### Project Library

The library is populated by calling ``projspec library list --json-out``. The same information
is used by the Details panel, and rerunning of the subprocess will only be as
specified here, since it is relatively expensive. While calling the subprocess,
the library area should show a busy spinner. The structure
of the JSON returned is a mapping from URL to Project entities.

The main component of this panel is a list of Project elements, one widget per
Project in the library.

Each project widget
has a short name (the basename of the URL) as a title at the top (bold),
the URL below this and storage_options (if the Project has any), and, finally
an area containing chips with rounded corners and backgrounds drawn from a pastel
palette. One chip may be "Contents <{x}>" is the Project in question has entries
under "contents" (where `x` is the number of items) and similarly "Artifacts <{x}>"
for field "artifacts". The remaining chips will be the keys in the "specs" field.
The mapping from chip label to colour should be deterministic.

In addition, each project widget has a "kebab" button in its top-right,
which opens a small popup menu with the following options, in the case that the
URL starts with "file://":
- Open with...
  - VCSode
  - System filebrowser
  - PyCharm
  - jupyter
- Rescan
- Create spec
- Remove from library
In the case of other URLs (i.e., remote objects), the kebab menu options are:
- Copy to local
- Rescan
- Remove from library

Above the main Projects listing areas, there is a search box with a right-justified
cancel (x) button.

Above the search box, The following buttons: "Add", "Reload", "Configure"

## Details panel

This panel contains a main list area similar in style to the Library. Above
this area is a title and details area, where the details may be minimised.

In the case that the selection in the Library is a spec,
the title of the panel is the same as the selected spec, and the info area
is filled with the doc+link for the spec's name, from the "projspec info" data.
The link (if it exists) is a clickable link. If it was the Content of Artifact
button, there is no title/detail.

The contents of this panel are drawn from the global "projspec library list" JSON data,
and the set of list widgets depends on what was selected in the Library panel.
If "Contents" is selected, we show the list
of contents for the selected project and the panel title is "Contents";
likewise for "Artifacts". If a spec's name
is selected, all of the Contents and Artifacts of that spec of the given Project
are shown. The field names in the JSON data are '_contents', '_artifacts'. Each key
of these may be:
- a single dict containing a "klass" key, in which case it is one widget with no
name
- a list, where each item has a "klass" and is a separate widget with no name
- a dict where each nested value has a "klass" in which case the key is the widget's
name.

The widget's title is the value of "klass", and its name, if it has one. The
content is the remainder of the JSON data in an expandable tree structure.
The widget should have an (i) info button, which only shows when the
mouse is over the widget; clicking it shows the documentation for the klass
derived from the "projspec info" data (there will be no link or create fields).
For artifact widgets, there is also a "Make" button to the left of the (i).

## Interactions

- startup: perform the info and library list commands to populate the Library panel. A busy
indicator shows.
- "add" button: open file selector dialog allowing directory selection. If accepted,
call subprocess "projspec scan --library <path>" and then reload the library
- "reload" button: reload the library
- "configure" button: open file ($PROJSPEC_CONFIG_DIR or ~/.config/projspec)/projspec.json for editing; if
it doesn't exist, populate with the following and then open for editing:
```
{
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
        "scan_max_files": 100,
        "scan_max_size": 5000,
        "remote_artifact_status": false,
        "capture_artifact_output": true,
        "preferred_install_methods": ["conda", "pip"],
}
```
- select a chip from a Project widget in the Library panel: update the Details panel with
the JSON information of that chip (contents list, artifacts list or project spec)
- menu item "Open with VSCode": run subprocess "code <path>" with the project's URL ("file://" removed)
- menu item "Open with system filebrowser": open the system's file browser at the project's URL ("file://" removed)
- menu item "Open with pycharm": run subprocess "pycharm <path> nosplash dontReopenProjects" with the project's URL ("file://" removed)
- menu item "Open with jupyter": run subprocess "jupyter lab <path>" with the project's URL ("file://" removed)
- menu item "rescan": run subprocess "projspec scan --library <path>" with the project's URL, and then refresh the
library pane
- menu item "create spec": open modal dialog with a text edit line, which auto-completes using the list of project specs in the
info which have "create": true, and are *not* already present in the selected project. If the dialog is accepted,
run subprocess "projspec create <spec> <path>" where <spec> is what was selected in the dialog and <path> is the
project's URL. After completion, refresh the Library.
- menu item "remove from library": run subprocess "projspec library delete <path>" where <path> is the project's URL
(including any protocol prefix)
- menu item "copy to local": not implemented (greyed out)
- (i) info button: find the selected content/artifact in the info data, and present it as a popup to the left of
the current mouse position. Clicking away closes the popup.
- "make" button: using the built-in terminal, run the subprocess "projspec make [<spec>.]<artifact>[.<name>]" where
spec is the class name of the spec to which the artifact belongs (top-level artifacts, i.e., those in the "artifacts"
chip, don't have this), <artifact> is the artifact's class, and <name> is the artifact's name, if it has one.
