projspec — Qt app
==================

Qt5 desktop UI for projspec, functionally equivalent to the `VSCode extension
<../vsextension>`_ and the `textual TUI <../textapp>`_.  The three UIs share
the same two-pane layout and action vocabulary — see
``vsextension/ACTIONS.md`` for the canonical reference.

Layout
------

``Library`` (left) and ``Details`` (right), rendered by a single
``QWebEngineView`` hosting the same HTML/CSS/JS ported from the VSCode
extension.  The Python side takes the role of the extension host: it calls
``projspec`` APIs in-process (no subprocess) and routes actions via
``QWebChannel`` messages.

- **Library**: toolbar (``Add``, ``Reload``, ``Configure``), search box, and
  one widget per project with chips for ``Contents``, ``Artifacts``, and each
  registered spec.  A kebab button opens a menu with ``Open with VSCode /
  system filebrowser / PyCharm / jupyter``, ``Rescan``, ``Create spec`` and
  ``Remove from library``.
- **Details**: when a chip is selected, shows the spec's doc + link and
  per-item widgets with coloured outlines (green for contents, red for
  artifacts), YAML-rendered data, and action buttons (``→`` to reveal a
  local file in the OS file browser, ``▶`` to invoke ``make``, ``ⓘ`` for
  the class docstring).  Enum values render as their member name.

Running
-------

.. code-block:: bash

    python qtapp/main.py

or, after installing the package with the ``qt`` extra::

    projspec-qt

Requirements: PyQt5 with the ``QtWebEngineWidgets`` module.
