projspec — Textual TUI
=======================

Terminal UI for projspec, functionally equivalent to the `VSCode extension
<../vsextension>`_ and the `Qt app <../qtapp>`_.  The three UIs share the
same two-pane layout and action vocabulary — see ``vsextension/ACTIONS.md``
for the canonical reference.

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

    projspec-tui

Requirements: `Textual <https://textual.textualize.io/>`_ ≥ 0.60.
