projspec — Textual TUI
=======================

Terminal UI for projspec, functionally equivalent to the `VSCode extension
<../vsextension>`_ and the `Qt app <../qtapp>`_.  The three UIs share the
same two-pane layout and action vocabulary — see ``vsextension/ACTIONS.md``
for the canonical reference.

Layout
------

```
┌──────────────────────────┬────────────────────────────┐
│ + Add  ↻ Reload  ⚙ …     │                            │
│ ┌ filter ┐   ×            │                            │
│                          │   title                    │
│ ┌─ my-project ─┐         │   doc / link               │
│ │ /path/...    │         │                            │
│ │ Contents <3> │         │   ┌─ environment ──────┐  │
│ │ python_lib … │         │   │  stack: CONDA      │  │
│ │   ⋮          │         │   │  packages: [...]   │  │
│ └──────────────┘         │   └────────────────────┘  │
│                          │                            │
└──────────────────────────┴────────────────────────────┘
```

- **Library** (left): toolbar (``Add`` / ``Reload`` / ``Configure``),
  filter input, and one widget per project with chips for ``Contents``,
  ``Artifacts``, and each registered spec.  A ``⋮`` button opens a menu with
  ``Open with VSCode / system filebrowser / PyCharm / jupyter``, ``Rescan``,
  ``Create spec`` and ``Remove from library``.
- **Details** (right): when a chip is selected, shows the spec's doc + link
  and per-item widgets with coloured outlines (green for contents, red for
  artifacts), YAML-rendered data, and action buttons (``→ Reveal`` to open
  the containing directory, ``▶ Make`` to invoke ``projspec make``,
  ``ⓘ Info`` for the class docstring).  Enum values render as their
  member name.

Key bindings
------------

=====  ======================================================================
Key    Action
=====  ======================================================================
``a``  Add a directory (or URL) to the library
``r``  Reload the library from disk
``/``  Focus the filter input
``q``  Quit
=====  ======================================================================

Running
-------

.. code-block:: bash

    python textapp/main.py

or, after installing the package with the ``textual`` extra::

    projspec-tui

Requirements: `Textual <https://textual.textualize.io/>`_ ≥ 0.60.
