"""Shared web UI resources for the projspec Project Library panel.

The VSCode extension, the Qt app, the PyCharm plugin and the ipywidget
representation of :class:`projspec.library.ProjectLibrary` all render the
same two-pane UI (library on the left, details on the right).  This package
owns the canonical HTML / CSS / JS / icon set used by all of them.

Public helpers
--------------

:func:`get_panel_html`
    Return a complete HTML document string with the shared panel embedded.
    Individual hosts pass extra ``<head>`` content (e.g. qwebchannel.js) and
    a short bootstrap snippet that installs ``window.projspecTransport``
    before the main panel script runs.

:func:`get_panel_css` / :func:`get_panel_js`
    Return the CSS and JS as plain strings, for hosts (PyCharm, ipywidget)
    that embed the panel without building a full HTML document.

:func:`chrome_icons`
    Return the chrome emoji map (toolbar icons, kebab glyph, etc.).

Transport contract
------------------

The shared JS does not know how it is being loaded.  The host must define
``window.projspecTransport`` *before* ``panel.js`` runs.  The transport is
an object of shape::

    {
        send:    function(msg) { ... },        // JS -> host
        onReady: function(dispatch) { ... },   // host calls dispatch(msg)
                                               // for every host -> JS msg
    }

Messages are plain objects; the command vocabulary matches the VSCode
extension's ``ACTIONS.md``.  Outbound (JS -> host) messages carry ``cmd``;
inbound messages carry ``type`` (``data``, ``loading``, or
``openCreateSpecModal``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

__all__ = [
    "chrome_icons",
    "get_panel_css",
    "get_panel_html",
    "get_panel_js",
    "resource_path",
]

_HERE = Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """Return the absolute path to a bundled webui resource.

    ``name`` is a filename inside this package (e.g. ``"panel.css"``).
    """
    return _HERE / name


@lru_cache(maxsize=1)
def _chrome_raw() -> str:
    return (_HERE / "chrome.json").read_text(encoding="utf-8")


def chrome_icons() -> dict[str, str]:
    """Return the chrome emoji map (toolbar icons, kebab glyph, etc.)."""
    return json.loads(_chrome_raw())


@lru_cache(maxsize=1)
def get_panel_css() -> str:
    """Return the shared panel stylesheet as a plain string."""
    return (_HERE / "panel.css").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def get_panel_js() -> str:
    """Return the shared panel JavaScript as a plain string."""
    return (_HERE / "panel.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _html_template() -> str:
    return (_HERE / "panel.html").read_text(encoding="utf-8")


def get_panel_html(
    *,
    extra_head: str = "",
    bootstrap_js: str = "",
    embedded: bool = False,
) -> str:
    """Return a self-contained HTML document hosting the projspec panel.

    Parameters
    ----------
    extra_head:
        Optional HTML injected into the ``<head>`` *before* the inline
        stylesheet.  Hosts that need an external script (for instance
        ``qwebchannel.js`` under Qt) should pass it here.
    bootstrap_js:
        Optional ``<script>`` block injected *before* the shared ``panel.js``
        runs.  The bootstrap must install ``window.projspecTransport`` (and
        optionally ``window.__PROJSPEC_CHROME_ICONS__``).  It may use
        ``<script>`` tags directly; the string is inserted verbatim.
    embedded:
        If ``True``, adds the ``embedded`` class to ``<body>``, which clamps
        the panel height to ``--projspec-panel-height`` (default 600px)
        instead of using ``100vh``.  Used by the ipywidget host.

    Notes
    -----
    Icons and emoji characters in the HTML template use the ``<!--ICON:xxx-->``
    marker; they are replaced here from :func:`chrome_icons`.  Hosts that
    want to override individual glyphs should do so in their ``bootstrap_js``
    by setting ``window.__PROJSPEC_CHROME_ICONS__``.
    """
    html = _html_template()
    icons = chrome_icons()
    for key, glyph in icons.items():
        html = html.replace(f"<!--ICON:{key}-->", glyph)

    html = html.replace("<!--EXTRA_HEAD-->", extra_head)
    html = html.replace("<!--BOOTSTRAP-->", bootstrap_js)
    html = html.replace("/*__CSS__*/", get_panel_css())
    html = html.replace("/*__JS__*/", get_panel_js())

    if embedded:
        html = html.replace("<body>", '<body class="embedded">', 1)
    return html
