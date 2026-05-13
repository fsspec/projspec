"""HTML/CSS/JS for the Qt webview panel.

The shared HTML/CSS/JS lives in :mod:`projspec.webui` and is reused by the
VSCode extension (in spirit — via TS port), the PyCharm plugin, the Qt app,
and the Jupyter ipywidget.  This module now only contributes the small
Qt-specific bootstrap that wires :class:`QWebChannel`'s ``bridge`` object
to the shared transport protocol.

Icons are emoji characters.  ``projspec`` itself stores an emoji in each
spec / content / artifact class's ``icon`` attribute, so the webview just
renders whatever ``class_infos()`` returns.  The small set of *chrome*
icons (toolbar buttons, kebab trigger, etc.) lives in
:mod:`projspec.webui`'s ``chrome.json`` so the four UIs share a single
source of truth.
"""

from __future__ import annotations

import json

from projspec.webui import chrome_icons, get_panel_html

# Re-exported for backwards compatibility with the handful of callers that
# still pull CHROME from here.
CHROME = chrome_icons()


# ---------------------------------------------------------------------------
#  Bootstrap script — installs window.projspecTransport for QWebChannel.
# ---------------------------------------------------------------------------
#
# QWebChannel's JS helper is loaded from a Qt resource URL.  Once the
# channel is up, the Python-side ``JsBridge`` object is available as
# ``channel.objects.bridge`` with two slots:
#
#   - ``bridge.handleMessage(json_string)``: JS -> Python
#   - ``bridge.from_python(signal)``: Python -> JS, emitted with a JSON
#     string
#
# The shared panel.js doesn't know about any of that; it only consults
# ``window.projspecTransport``.  The bootstrap below adapts QWebChannel
# to the transport protocol.

_QT_EXTRA_HEAD = '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'

_QT_BOOTSTRAP = r"""
<script>
window.__PROJSPEC_CHROME_ICONS__ = __CHROME_ICONS_JSON__;
(function() {
    // Buffer outbound messages + inbound dispatcher until the channel is up.
    let bridge = null;
    let dispatch = null;
    const pending = [];
    const inbox = [];

    window.projspecTransport = {
        send: (msg) => {
            if (bridge) bridge.handleMessage(JSON.stringify(msg));
            else pending.push(msg);
        },
        onReady: (d) => {
            dispatch = d;
            // Deliver any messages that arrived before dispatch was set.
            while (inbox.length) dispatch(inbox.shift());
        },
    };

    new QWebChannel(qt.webChannelTransport, (channel) => {
        bridge = channel.objects.bridge;
        bridge.from_python.connect((raw) => {
            let msg;
            try { msg = JSON.parse(raw); } catch { return; }
            if (dispatch) dispatch(msg);
            else inbox.push(msg);
        });
        while (pending.length) bridge.handleMessage(JSON.stringify(pending.shift()));
    });
})();
</script>
"""


def get_panel_html() -> str:
    """Return the full HTML document served to the Qt webview.

    Delegates to :func:`projspec.webui.get_panel_html`, supplying the
    Qt-specific ``<head>`` (for ``qwebchannel.js``) and bootstrap script
    that installs the QWebChannel-backed transport.
    """
    bootstrap = _QT_BOOTSTRAP.replace(
        "__CHROME_ICONS_JSON__",
        json.dumps(chrome_icons(), separators=(",", ":")),
    )
    from projspec import webui

    return webui.get_panel_html(
        extra_head=_QT_EXTRA_HEAD,
        bootstrap_js=bootstrap,
    )


__all__ = ["CHROME", "get_panel_html"]
