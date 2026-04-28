"""HTML/CSS/JS for the Qt webview panel.

The markup, styles and webview-side script mirror the VSCode extension's
panel (``vsextension/src/panel.ts``).  Keeping them in lock-step means the
two UIs look and behave identically; the only real difference is the host
bridge (``QWebChannel``'s ``bridge`` object vs VSCode's ``acquireVsCodeApi``).

Icons are emoji characters.  ``projspec`` itself stores an emoji in each
spec / content / artifact class's ``icon`` attribute, so the webview just
renders whatever ``class_infos()`` returns.  The small set of *chrome*
icons (toolbar buttons, kebab trigger, etc.) lives in
:mod:`qtapp.emoji` so the three UIs share a single source of truth.
"""

from __future__ import annotations

import json

from emoji import CHROME


def get_panel_html() -> str:
    """Return the full HTML document served to the Qt webview.

    The bridge is registered on Python-side as ``bridge`` (class
    :class:`~main.JsBridge`).  The script below waits for QWebChannel to wire
    it up and then mirrors the same API the VSCode webview uses
    (``postMessage`` / ``window.addEventListener('message', ...)``).
    """
    html = _HTML_TEMPLATE
    for key, glyph in CHROME.items():
        html = html.replace(f"<!--ICON:{key}-->", glyph)
    js = _PANEL_JS.replace(
        "__CHROME_ICONS_JSON__", json.dumps(CHROME, separators=(",", ":"))
    )
    return html.replace("/*__CSS__*/", _PANEL_CSS).replace("/*__JS__*/", js)


# ---------------------------------------------------------------------------
#  HTML skeleton
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Project Library</title>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>/*__CSS__*/</style>
</head>
<body>
<div id="app">
    <div id="library">
        <div class="toolbar">
            <button id="btn-add"><!--ICON:add--> Add</button>
            <button id="btn-reload"><!--ICON:reload--> Reload</button>
            <button id="btn-configure"><!--ICON:configure--> Configure</button>
        </div>
        <div class="search">
            <!--ICON:search-->
            <input type="text" id="search" placeholder="Filter projects..." />
            <button id="search-clear" title="Clear"><!--ICON:clear--></button>
        </div>
        <div id="projects"></div>
        <div id="spinner" class="hidden">
            <span class="icon spin"><!--ICON:spinner--></span>
            Loading...
        </div>
    </div>
    <div id="details">
        <div id="details-header">
            <div id="details-title">Details</div>
            <button id="details-toggle" title="Toggle info"><!--ICON:chevron_up--></button>
        </div>
        <div id="details-info"></div>
        <div id="details-list"></div>
    </div>
</div>
<div id="popup" class="hidden"></div>
<div id="modal-overlay" class="hidden">
    <div id="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div id="modal-title">Create spec</div>
        <div id="modal-body">
            <label for="modal-input">Spec type:</label>
            <input type="text" id="modal-input" autocomplete="off" spellcheck="false" placeholder="Start typing..." />
            <div id="modal-suggestions"></div>
        </div>
        <div id="modal-actions">
            <button id="modal-cancel" class="secondary">Cancel</button>
            <button id="modal-ok" class="primary" disabled>Create</button>
        </div>
    </div>
</div>
<script>/*__JS__*/</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
#  CSS - ported from vsextension/src/panel.ts getPanelCss()
# ---------------------------------------------------------------------------
#
# Qt webviews don't have VSCode's CSS theme variables, so every
# ``var(--vscode-...)`` is given a sensible fallback that produces a dark
# theme similar to VSCode's default dark+ palette.
#

_PANEL_CSS = r"""
* { box-sizing: border-box; }

body {
    margin: 0; padding: 0;
    font-family: -apple-system, 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #cccccc;
    background: #1e1e1e;
}

/* Emoji icons don't need any wrapper styling for themselves, but we still
   want the spinner to rotate. */
.icon.spin {
    display: inline-block;
    animation: spin 1.2s linear infinite;
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

#app { display: flex; height: 100vh; overflow: hidden; }
#library {
    width: 40%; min-width: 320px; max-width: 520px;
    border-right: 1px solid #3c3c3c;
    display: flex; flex-direction: column; overflow: hidden;
}
#details { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.toolbar {
    display: flex; gap: 6px; padding: 8px;
    border-bottom: 1px solid #3c3c3c;
}
.toolbar button {
    background: #3c3c3c; color: #cccccc;
    border: none; padding: 4px 10px; cursor: pointer;
    font-size: 12px; border-radius: 3px;
}
.toolbar button:hover { background: #505050; }

.search {
    display: flex; align-items: center; gap: 6px; padding: 6px 8px;
    border-bottom: 1px solid #3c3c3c;
}
.search input {
    flex: 1; background: #3c3c3c; color: #cccccc;
    border: 1px solid transparent; padding: 4px 8px;
    font-size: 12px; border-radius: 2px;
}
.search button {
    background: transparent; color: #858585;
    border: none; cursor: pointer; padding: 2px 4px;
}
.search button:hover { color: #cccccc; }

#projects { flex: 1; overflow-y: auto; padding: 6px; }
#spinner { text-align: center; padding: 16px; color: #858585; }
.hidden { display: none !important; }

.project {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 6px;
    cursor: pointer;
    position: relative;
    background: #252526;
}
.project:hover { background: #2a2d2e; }
.project.active {
    border-color: #007acc;
    background: #094771;
}
.project .title { font-weight: bold; margin-right: 24px; }
.project .url { font-size: 11px; color: #858585; word-break: break-all; margin-top: 2px; }
.project .storage-opts { font-size: 11px; color: #858585; margin-top: 2px; font-style: italic; }
.project .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }

.chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: #c5e0c1; color: #222;
    padding: 2px 8px; border-radius: 10px;
    font-size: 11px; cursor: pointer;
    border: 1px solid transparent;
    user-select: none;
}
.chip:hover { filter: brightness(0.95); }
.chip.active { border-color: #007acc; box-shadow: 0 0 0 1px #007acc; }

.kebab {
    position: absolute; top: 6px; right: 6px;
    background: transparent; border: none; color: #cccccc;
    cursor: pointer; padding: 2px 6px; border-radius: 3px;
}
.kebab:hover { background: #3c3c3c; }
.kebab-menu {
    position: absolute; right: 6px; top: 28px;
    background: #252526; color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 3px; padding: 4px 0; z-index: 10;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3); min-width: 200px;
}
.kebab-menu .menu-item {
    padding: 4px 12px; cursor: pointer; font-size: 12px; white-space: nowrap;
}
.kebab-menu .menu-item:hover { background: #094771; color: #ffffff; }
.kebab-menu .menu-item.disabled { color: #6a6a6a; cursor: default; }
.kebab-menu .menu-item.disabled:hover { background: transparent; color: #6a6a6a; }
.kebab-menu .menu-sep { height: 1px; margin: 4px 0; background: #3c3c3c; }

#details-header {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-bottom: 1px solid #3c3c3c;
}
#details-title { font-weight: bold; font-size: 14px; flex: 1; }
#details-toggle {
    background: transparent; border: none; color: #cccccc; cursor: pointer;
    padding: 2px 6px;
}
#details-info {
    padding: 8px 12px; border-bottom: 1px solid #3c3c3c;
    color: #858585; font-size: 12px;
}
#details-info a { color: #3794ff; }
#details-info.collapsed { display: none; }
#details-list { flex: 1; overflow-y: auto; padding: 8px 12px; }

.item-widget {
    position: relative;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-bottom: 8px;
    padding: 8px 10px;
    background: #252526;
}
.item-widget.kind-content { border-color: #4ca97a; box-shadow: 0 0 0 1px rgba(76,169,122,0.15); }
.item-widget.kind-artifact { border-color: #c66060; box-shadow: 0 0 0 1px rgba(198,96,96,0.15); }
.item-widget .widget-html { margin-top: 6px; font-size: 12px; line-height: 1.4; }
.item-widget .widget-html img { max-width: 100%; height: auto; }
.item-widget .widget-html a { color: #3794ff; }
.item-widget .widget-html table { border-collapse: collapse; }
.item-widget .widget-html th, .item-widget .widget-html td {
    border: 1px solid #3c3c3c; padding: 2px 6px;
}
.item-widget .widget-title { font-weight: bold; font-size: 13px; }
.item-widget .widget-subtitle { font-size: 11px; color: #858585; }
.item-widget .widget-actions {
    position: absolute; top: 6px; right: 6px; display: flex; gap: 4px;
    opacity: 0; transition: opacity 0.1s;
}
.item-widget:hover .widget-actions { opacity: 1; }
.item-widget .widget-actions button {
    background: transparent; border: none; color: #cccccc;
    cursor: pointer; padding: 2px 6px; border-radius: 3px;
}
.item-widget .widget-actions button:hover { background: #3c3c3c; }

.tree { font-family: monospace; font-size: 12px; margin-top: 6px; }
.tree .key { color: #9cdcfe; }
.tree .value.str { color: #ce9178; }
.tree .value.num { color: #b5cea8; }
.tree .value.bool, .tree .value.null { color: #569cd6; }
.tree .value.enum { color: #4ec9b0; font-weight: 600; }
.tree .value.empty { color: #858585; font-style: italic; }

.tree.yaml .yaml-item { position: relative; padding-left: 0; }
.tree.yaml .yaml-item.list-item { display: flex; align-items: flex-start; flex-wrap: wrap; }
.tree.yaml .yaml-item .marker {
    color: #858585; user-select: none; padding-right: 2px;
}
.tree.yaml .yaml-item.collapsible > .marker,
.tree.yaml .yaml-item.collapsible > .label { cursor: pointer; }
.tree.yaml .yaml-item.collapsible > .marker::after,
.tree.yaml .yaml-item.collapsible > .label::after {
    content: ' \25BE'; font-size: 9px; color: #858585;
}
.tree.yaml .yaml-item.collapsible.collapsed > .marker::after,
.tree.yaml .yaml-item.collapsible.collapsed > .label::after { content: ' \25B8'; }
.tree.yaml .yaml-item.collapsible.collapsed > .children { display: none; }
.tree.yaml .yaml-item .body.empty { display: none; }
.tree.yaml .yaml-item > .children { padding-left: 16px; width: 100%; }

#popup {
    position: fixed; background: #252526; color: #cccccc;
    border: 1px solid #454545; padding: 8px 10px; border-radius: 4px;
    max-width: 360px; z-index: 1000;
    box-shadow: 0 4px 10px rgba(0,0,0,0.4); font-size: 12px;
}
#popup a { color: #3794ff; }

/* Create-spec modal - identical rules to the VSCode extension */
#modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center;
    z-index: 2000;
}
#modal {
    background: #252526; color: #cccccc; border: 1px solid #454545;
    border-radius: 6px; min-width: 360px; max-width: 80%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    display: flex; flex-direction: column;
}
#modal-title {
    padding: 10px 14px; font-weight: bold; font-size: 14px;
    border-bottom: 1px solid #3c3c3c;
}
#modal-body { padding: 12px 14px; }
#modal-body label { display: block; font-size: 12px; margin-bottom: 4px; color: #858585; }
#modal-input {
    width: 100%; box-sizing: border-box;
    background: #3c3c3c; color: #cccccc; border: 1px solid transparent;
    padding: 6px 8px; font-size: 13px; border-radius: 3px; outline: none;
}
#modal-input:focus { border-color: #007acc; }
#modal-suggestions {
    margin-top: 6px; max-height: 220px; overflow-y: auto;
    border: 1px solid #3c3c3c; border-radius: 3px;
    font-size: 12px; background: #3c3c3c;
}
#modal-suggestions .suggestion { padding: 4px 8px; cursor: pointer; }
#modal-suggestions .suggestion:hover,
#modal-suggestions .suggestion.active { background: #094771; color: #ffffff; }
#modal-suggestions .empty { padding: 4px 8px; color: #858585; font-style: italic; }
#modal-actions {
    display: flex; justify-content: flex-end; gap: 6px;
    padding: 10px 14px; border-top: 1px solid #3c3c3c;
}
#modal-actions button {
    border: none; cursor: pointer; padding: 6px 14px; font-size: 12px;
    border-radius: 3px;
}
#modal-actions button.primary { background: #0e639c; color: #ffffff; }
#modal-actions button.primary:hover:not(:disabled) { background: #1177bb; }
#modal-actions button.primary:disabled { opacity: 0.5; cursor: default; }
#modal-actions button.secondary {
    background: transparent; color: #cccccc; border: 1px solid #3c3c3c;
}
#modal-actions button.secondary:hover { background: #3c3c3c; }
"""


# ---------------------------------------------------------------------------
#  JavaScript - ported from vsextension/src/panel.ts PANEL_JS
# ---------------------------------------------------------------------------
#
# Differences from the VSCode version:
#   - Uses QWebChannel instead of ``acquireVsCodeApi``.  Python -> JS
#     messages arrive on the bridge's ``from_python`` signal; JS -> Python
#     go through ``bridge.handleMessage`` with a JSON string.
#   - Boot sequence waits for ``new QWebChannel()`` before posting the
#     initial ``ready`` handshake.
#

_PANEL_JS = r"""
(function() {
    let bridge = null;
    let info = null;
    let enums = {};
    let library = {};
    let selection = null;

    // Emoji icons used by the UI itself (not per-spec/content/artifact -
    // those come from ``entry.icon``).  Injected here rather than in a
    // separate shared file so the Python / TS ports of this JS don't need
    // additional JSON loading at runtime.
    const CHROME_ICONS = __CHROME_ICONS_JSON__;
    const DEFAULT_ICONS = { spec: '🧩', content: '📄', artifact: '📦' };

    // Post a message to Python once the bridge is available.  Pre-bridge
    // messages are queued and flushed on connection.
    const pending = [];
    function postMessage(msg) {
        if (bridge) { bridge.handleMessage(JSON.stringify(msg)); }
        else { pending.push(msg); }
    }

    new QWebChannel(qt.webChannelTransport, (channel) => {
        bridge = channel.objects.bridge;
        bridge.from_python.connect((raw) => {
            let msg;
            try { msg = JSON.parse(raw); } catch { return; }
            dispatch(msg);
        });
        while (pending.length) bridge.handleMessage(JSON.stringify(pending.shift()));
        postMessage({ cmd: 'ready' });
    });

    function dispatch(msg) {
        if (msg.type === 'loading') {
            spinnerEl.classList.toggle('hidden', !msg.loading);
        } else if (msg.type === 'data') {
            info = msg.info;
            enums = msg.enums || {};
            library = msg.library || {};
            if (selection && !library[selection.url]) selection = null;
            render();
        } else if (msg.type === 'openCreateSpecModal') {
            openCreateSpecModal(msg.url, msg.specs || []);
        }
    }

    // ----- pastel palette for chip colours -----
    const PALETTE = [
        '#f9c0c0', '#f9dcc0', '#f9f0c0', '#d9f9c0', '#c0f9d2',
        '#c0f9f0', '#c0e3f9', '#c0ccf9', '#d6c0f9', '#efc0f9',
        '#f9c0e3', '#d9c9b5', '#b5d9c9', '#b5c9d9', '#c9b5d9',
    ];
    function hashStr(s) {
        let h = 0;
        for (let i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
        return Math.abs(h);
    }
    function chipColour(label) { return PALETTE[hashStr(label) % PALETTE.length]; }

    function basename(url) {
        try {
            const stripped = url.replace(/\/+$/, '');
            const idx = stripped.lastIndexOf('/');
            return idx >= 0 ? stripped.slice(idx + 1) : stripped;
        } catch { return url; }
    }
    function iconForSpec(snake) {
        const entry = info && info.specs && info.specs[snake];
        return (entry && entry.icon) || DEFAULT_ICONS.spec;
    }
    function iconForContent(snake) {
        const entry = info && info.content && info.content[snake];
        return (entry && entry.icon) || DEFAULT_ICONS.content;
    }
    function iconForArtifact(snake) {
        const entry = info && info.artifact && info.artifact[snake];
        return (entry && entry.icon) || DEFAULT_ICONS.artifact;
    }

    // ----- DOM refs -----
    const projectsEl = document.getElementById('projects');
    const spinnerEl = document.getElementById('spinner');
    const searchEl = document.getElementById('search');
    const searchClear = document.getElementById('search-clear');
    const detailsTitle = document.getElementById('details-title');
    const detailsInfo = document.getElementById('details-info');
    const detailsList = document.getElementById('details-list');
    const detailsToggle = document.getElementById('details-toggle');
    const popup = document.getElementById('popup');

    detailsToggle.addEventListener('click', () => {
        detailsInfo.classList.toggle('collapsed');
        const collapsed = detailsInfo.classList.contains('collapsed');
        detailsToggle.textContent = collapsed ? CHROME_ICONS.chevron_down : CHROME_ICONS.chevron_up;
    });

    function render() {
        const filter = (searchEl.value || '').trim().toLowerCase();
        projectsEl.innerHTML = '';
        const urls = Object.keys(library).sort();
        let any = false;
        for (const url of urls) {
            const project = library[url];
            if (filter) {
                const hay = (url + ' ' + basename(url) + ' ' + Object.keys(project.specs || {}).join(' ')).toLowerCase();
                if (!hay.includes(filter)) continue;
            }
            any = true;
            projectsEl.appendChild(renderProject(url, project));
        }
        if (!any) {
            const e = document.createElement('div');
            e.style.padding = '20px';
            e.style.color = '#858585';
            e.style.textAlign = 'center';
            e.textContent = urls.length === 0
                ? 'Library is empty. Click "Add" to scan a directory.'
                : 'No projects match the filter.';
            projectsEl.appendChild(e);
        }
        if (selection) renderDetails();
    }

    function renderProject(url, project) {
        const wrap = document.createElement('div');
        wrap.className = 'project';
        wrap.dataset.url = url;

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = basename(url);
        wrap.appendChild(title);

        const urlLine = document.createElement('div');
        urlLine.className = 'url';
        urlLine.textContent = url;
        wrap.appendChild(urlLine);

        if (project.storage_options && Object.keys(project.storage_options).length > 0) {
            const so = document.createElement('div');
            so.className = 'storage-opts';
            so.textContent = 'storage_options: ' + JSON.stringify(project.storage_options);
            wrap.appendChild(so);
        }

        const chips = document.createElement('div');
        chips.className = 'chips';
        const contents = project.contents || {};
        const artifacts = project.artifacts || {};
        if (Object.keys(contents).length > 0)
            chips.appendChild(makeChip('Contents <' + Object.keys(contents).length + '>', url, 'contents', null, null));
        if (Object.keys(artifacts).length > 0)
            chips.appendChild(makeChip('Artifacts <' + Object.keys(artifacts).length + '>', url, 'artifacts', null, null));
        for (const specName of Object.keys(project.specs || {})) {
            chips.appendChild(makeChip(specName, url, 'spec', specName, iconForSpec(specName)));
        }
        wrap.appendChild(chips);

        const kebabBtn = document.createElement('button');
        kebabBtn.className = 'kebab';
        kebabBtn.textContent = CHROME_ICONS.kebab;
        kebabBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            toggleKebab(wrap, url);
        });
        wrap.appendChild(kebabBtn);

        if (selection && selection.url === url) wrap.classList.add('active');
        return wrap;
    }

    function makeChip(label, url, kind, specName, icon) {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.style.background = chipColour(label);
        if (icon)
            chip.innerHTML = '<span class="chip-icon">' + escapeHtml(icon) + '</span><span>' + escapeHtml(label) + '</span>';
        else chip.textContent = label;
        chip.addEventListener('click', (ev) => {
            ev.stopPropagation();
            selection = { url, kind, specName };
            document.querySelectorAll('.project.active').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.chip.active').forEach(el => el.classList.remove('active'));
            const projEl = ev.target.closest('.project');
            if (projEl) projEl.classList.add('active');
            chip.classList.add('active');
            renderDetails();
        });
        if (selection && selection.url === url &&
            ((selection.kind === kind && kind !== 'spec') ||
             (selection.kind === 'spec' && kind === 'spec' && selection.specName === specName))) {
            chip.classList.add('active');
        }
        return chip;
    }

    // ----- kebab menu -----
    let openKebab = null;
    function toggleKebab(projectEl, url) {
        if (openKebab && openKebab.el === projectEl) { closeKebab(); return; }
        closeKebab();
        const menu = document.createElement('div');
        menu.className = 'kebab-menu';
        const isLocal = url.startsWith('file://');
        if (isLocal) {
            addItem(menu, 'Open with VSCode', () => postMessage({ cmd: 'openWith', tool: 'vscode', url }));
            addItem(menu, 'Open with system filebrowser', () => postMessage({ cmd: 'openWith', tool: 'filebrowser', url }));
            addItem(menu, 'Open with PyCharm', () => postMessage({ cmd: 'openWith', tool: 'pycharm', url }));
            addItem(menu, 'Open with jupyter', () => postMessage({ cmd: 'openWith', tool: 'jupyter', url }));
            addSeparator(menu);
            addItem(menu, 'Rescan', () => postMessage({ cmd: 'rescan', url }));
            addItem(menu, 'Create spec', () => postMessage({ cmd: 'createSpec', url }));
            addItem(menu, 'Remove from library', () => postMessage({ cmd: 'removeFromLibrary', url }));
        } else {
            const ctl = addItem(menu, 'Copy to local', () => postMessage({ cmd: 'copyToLocal', url }));
            ctl.classList.add('disabled');
            addItem(menu, 'Rescan', () => postMessage({ cmd: 'rescan', url }));
            addItem(menu, 'Remove from library', () => postMessage({ cmd: 'removeFromLibrary', url }));
        }
        projectEl.appendChild(menu);
        openKebab = { el: projectEl, menu };
        setTimeout(() => document.addEventListener('click', closeKebab, { once: true }), 0);
    }
    function addItem(menu, label, onClick) {
        const mi = document.createElement('div');
        mi.className = 'menu-item';
        mi.textContent = label;
        mi.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!mi.classList.contains('disabled')) { onClick(); closeKebab(); }
        });
        menu.appendChild(mi);
        return mi;
    }
    function addSeparator(menu) {
        const sep = document.createElement('div');
        sep.className = 'menu-sep';
        menu.appendChild(sep);
    }
    function closeKebab() {
        if (openKebab) { openKebab.menu.remove(); openKebab = null; }
    }

    // ----- details -----
    function renderDetails() {
        detailsList.innerHTML = '';
        detailsInfo.innerHTML = '';
        if (!selection) { detailsTitle.textContent = 'Details'; return; }
        const project = library[selection.url];
        if (!project) { detailsTitle.textContent = 'Details'; return; }

        if (selection.kind === 'spec') {
            detailsTitle.textContent = selection.specName;
            const entry = info && info.specs && info.specs[selection.specName];
            if (entry) {
                const doc = document.createElement('div');
                doc.textContent = entry.doc || '';
                detailsInfo.appendChild(doc);
                if (entry.link) {
                    const a = document.createElement('a');
                    a.href = entry.link;
                    a.textContent = entry.link;
                    a.target = '_blank';
                    detailsInfo.appendChild(document.createElement('br'));
                    detailsInfo.appendChild(a);
                }
            }
            const spec = project.specs[selection.specName];
            if (spec) {
                renderItemGroup(spec._contents || {}, 'content', false, selection.specName);
                renderItemGroup(spec._artifacts || {}, 'artifact', true, selection.specName);
            }
        } else if (selection.kind === 'contents') {
            detailsTitle.textContent = 'Contents';
            renderItemGroup(project.contents || {}, 'content', false, undefined);
        } else if (selection.kind === 'artifacts') {
            detailsTitle.textContent = 'Artifacts';
            renderItemGroup(project.artifacts || {}, 'artifact', true, undefined);
        }
    }

    function renderItemGroup(items, kind, showMake, specName) {
        if (!items || typeof items !== 'object') return;
        const keys = Object.keys(items);
        if (keys.length === 0) return;
        if (!hasKlass(items)) {
            detailsList.appendChild(makePlainWidget(items));
            return;
        }
        for (const typeName of keys) {
            const entry = items[typeName];
            if (!entry) continue;
            if (Array.isArray(entry)) {
                for (const e of entry)
                    detailsList.appendChild(makeItemWidget(typeName, null, e, kind, showMake, specName));
            } else if (entry && typeof entry === 'object' && 'klass' in entry) {
                detailsList.appendChild(makeItemWidget(typeName, null, entry, kind, showMake, specName));
            } else if (entry && typeof entry === 'object') {
                for (const name of Object.keys(entry))
                    detailsList.appendChild(makeItemWidget(typeName, name, entry[name], kind, showMake, specName));
            } else {
                detailsList.appendChild(makePlainWidget({ [typeName]: entry }));
            }
        }
    }

    function hasKlass(v) {
        if (!v || typeof v !== 'object') return false;
        if (!Array.isArray(v) && 'klass' in v) return true;
        if (Array.isArray(v)) { for (const e of v) if (hasKlass(e)) return true; return false; }
        for (const k of Object.keys(v)) if (hasKlass(v[k])) return true;
        return false;
    }

    function makePlainWidget(data) {
        const w = document.createElement('div');
        w.className = 'item-widget';
        const tree = document.createElement('div');
        tree.className = 'tree yaml';
        tree.appendChild(renderYaml(data));
        w.appendChild(tree);
        return w;
    }

    function makeItemWidget(typeName, name, data, kind, showMake, specName) {
        const w = document.createElement('div');
        w.className = 'item-widget kind-' + kind;

        const title = document.createElement('div');
        title.className = 'widget-title';
        const klass = (data && data.klass && Array.isArray(data.klass)) ? data.klass[1] : typeName;
        const iconName = kind === 'content' ? iconForContent(klass) : iconForArtifact(klass);
        title.innerHTML = '<span class="widget-icon">' + escapeHtml(iconName) + '</span> ' + escapeHtml(klass)
            + (name ? ' <span class="widget-subtitle">- ' + escapeHtml(name) + '</span>' : '');
        w.appendChild(title);

        const actions = document.createElement('div');
        actions.className = 'widget-actions';

        const fn = (data && typeof data === 'object') ? data.fn : undefined;
        if (kind === 'artifact' && typeof fn === 'string' && fn.length > 0 && isLocalPath(fn)) {
            const rv = document.createElement('button');
            rv.title = 'Reveal ' + fn;
            rv.textContent = CHROME_ICONS.reveal;
            rv.addEventListener('click', (e) => {
                e.stopPropagation();
                postMessage({ cmd: 'revealFile', fn });
            });
            actions.appendChild(rv);
        }

        if (showMake) {
            const mk = document.createElement('button');
            mk.title = 'Make';
            mk.textContent = CHROME_ICONS.play;
            mk.addEventListener('click', (e) => {
                e.stopPropagation();
                postMessage({
                    cmd: 'make',
                    url: selection.url,
                    spec: specName,
                    artifactType: typeName,
                    name: name || undefined,
                });
            });
            actions.appendChild(mk);
        }
        const ib = document.createElement('button');
        ib.title = 'Info';
        ib.textContent = CHROME_ICONS.info;
        ib.addEventListener('click', (e) => {
            e.stopPropagation();
            showInfoPopup(klass, kind, e.clientX, e.clientY);
        });
        actions.appendChild(ib);
        w.appendChild(actions);

        const html = (kind === 'content' && data && typeof data === 'object') ? data._html : undefined;
        if (typeof html === 'string') {
            const body = document.createElement('div');
            body.className = 'widget-html';
            body.innerHTML = sanitizeHtml(html);
            w.appendChild(body);
        } else {
            const tree = document.createElement('div');
            tree.className = 'tree yaml';
            tree.appendChild(renderYaml(stripKlass(data)));
            w.appendChild(tree);
        }
        return w;
    }

    function sanitizeHtml(html) {
        const tpl = document.createElement('template');
        tpl.innerHTML = String(html);
        const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT);
        const toRemove = [];
        let n = walker.nextNode();
        while (n) {
            const tag = n.tagName.toLowerCase();
            if (['script','iframe','object','embed'].includes(tag)) toRemove.push(n);
            else {
                for (const attr of Array.from(n.attributes)) {
                    const an = attr.name.toLowerCase();
                    if (an.startsWith('on')) { n.removeAttribute(attr.name); continue; }
                    if ((an === 'href' || an === 'src') && /^\s*javascript:/i.test(attr.value))
                        n.removeAttribute(attr.name);
                }
            }
            n = walker.nextNode();
        }
        for (const el of toRemove) el.remove();
        return tpl.innerHTML;
    }

    function stripKlass(obj) {
        if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return obj;
        const out = {};
        for (const k of Object.keys(obj)) if (k !== 'klass') out[k] = obj[k];
        return out;
    }

    function renderYaml(data) {
        const frag = document.createDocumentFragment();
        if (Array.isArray(data)) {
            if (data.length === 0) { frag.appendChild(textNode('[]', 'value empty')); return frag; }
            for (const item of data) frag.appendChild(yamlListItem(item));
            return frag;
        }
        if (data && typeof data === 'object') {
            const keys = Object.keys(data);
            if (keys.length === 0) { frag.appendChild(textNode('{}', 'value empty')); return frag; }
            for (const k of keys) frag.appendChild(yamlMapItem(k, data[k]));
            return frag;
        }
        frag.appendChild(primitiveSpan(data));
        return frag;
    }

    function yamlListItem(value) {
        const node = document.createElement('div');
        node.className = 'yaml-item list-item';
        const marker = document.createElement('span');
        marker.className = 'marker';
        marker.textContent = '- ';
        const body = document.createElement('span');
        body.className = 'body';
        if (isEnum(value)) {
            body.appendChild(enumSpan(value));
            node.appendChild(marker); node.appendChild(body);
            return node;
        }
        if (value && typeof value === 'object') {
            node.classList.add('collapsible');
            node.appendChild(marker);
            body.classList.add('empty');
            node.appendChild(body);
            const children = document.createElement('div');
            children.className = 'children';
            children.appendChild(renderYaml(value));
            node.appendChild(children);
            marker.addEventListener('click', (e) => {
                e.stopPropagation();
                node.classList.toggle('collapsed');
            });
            return node;
        }
        body.appendChild(primitiveSpan(value));
        node.appendChild(marker); node.appendChild(body);
        return node;
    }

    function yamlMapItem(key, value) {
        const node = document.createElement('div');
        node.className = 'yaml-item map-item';
        const label = document.createElement('div');
        label.className = 'label';
        if (isEnum(value)) {
            label.innerHTML = '<span class="key">' + escapeHtml(key) + '</span>: ';
            label.appendChild(enumSpan(value));
            node.appendChild(label);
            return node;
        }
        if (value && typeof value === 'object') {
            node.classList.add('collapsible');
            label.innerHTML = '<span class="key">' + escapeHtml(key) + '</span>:';
            node.appendChild(label);
            const children = document.createElement('div');
            children.className = 'children';
            children.appendChild(renderYaml(value));
            node.appendChild(children);
            label.addEventListener('click', (e) => {
                e.stopPropagation();
                node.classList.toggle('collapsed');
            });
            return node;
        }
        label.innerHTML = '<span class="key">' + escapeHtml(key) + '</span>: ';
        label.appendChild(primitiveSpan(value));
        node.appendChild(label);
        return node;
    }

    function isEnum(v) {
        return v && typeof v === 'object' && !Array.isArray(v)
            && Array.isArray(v.klass) && v.klass[0] === 'enum' && ('value' in v);
    }

    function enumSpan(v) {
        const name = v.klass[1];
        const raw = v.value;
        let label = null;
        const members = enums && enums[name];
        if (members) {
            for (const mname of Object.keys(members)) {
                if (members[mname] === raw) { label = mname; break; }
            }
        }
        const span = document.createElement('span');
        span.className = 'value enum';
        span.title = name + ' = ' + String(raw);
        span.textContent = label !== null ? label : String(raw);
        return span;
    }

    function primitiveSpan(v) {
        const s = document.createElement('span');
        s.className = 'value';
        if (typeof v === 'string') { s.classList.add('str'); s.textContent = v; }
        else if (typeof v === 'number') { s.classList.add('num'); s.textContent = String(v); }
        else if (typeof v === 'boolean') { s.classList.add('bool'); s.textContent = String(v); }
        else if (v === null || v === undefined) { s.classList.add('null'); s.textContent = 'null'; }
        else { s.textContent = String(v); }
        return s;
    }

    function textNode(text, cls) {
        const s = document.createElement('span');
        if (cls) s.className = cls;
        s.textContent = text;
        return s;
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g,
            (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function isLocalPath(p) {
        if (p.startsWith('file://')) return true;
        return !/^[a-z][a-z0-9+.-]*:\/\//i.test(p);
    }

    // ----- info popup -----
    function showInfoPopup(klass, kind, mx, my) {
        const map = kind === 'content' ? (info && info.content) : (info && info.artifact);
        const entry = map && map[klass];
        if (!entry) {
            popup.innerHTML = '<em>No info for ' + escapeHtml(klass) + '</em>';
        } else {
            popup.innerHTML = '<div style="font-weight:bold;margin-bottom:4px;">'
                + escapeHtml(klass) + '</div>'
                + '<div style="white-space:pre-wrap;">' + escapeHtml(entry.doc || '') + '</div>';
        }
        popup.classList.remove('hidden');
        popup.style.left = '-9999px'; popup.style.top = '-9999px';
        requestAnimationFrame(() => {
            const w = popup.offsetWidth, h = popup.offsetHeight;
            let x = mx - w - 8, y = my - 8;
            if (x < 4) x = 4;
            if (y + h > window.innerHeight - 4) y = window.innerHeight - h - 4;
            if (y < 4) y = 4;
            popup.style.left = x + 'px'; popup.style.top = y + 'px';
        });
        setTimeout(() => document.addEventListener('click', () => popup.classList.add('hidden'), { once: true }), 0);
    }

    // ----- create-spec modal -----
    const modalOverlay = document.getElementById('modal-overlay');
    const modalInput = document.getElementById('modal-input');
    const modalSuggestions = document.getElementById('modal-suggestions');
    const modalOk = document.getElementById('modal-ok');
    const modalCancel = document.getElementById('modal-cancel');
    let modalState = null;

    function openCreateSpecModal(url, specs) {
        modalState = { url, specs: specs.slice(), filtered: specs.slice(), active: 0 };
        modalInput.value = ''; modalOk.disabled = true;
        renderSuggestions();
        modalOverlay.classList.remove('hidden');
        setTimeout(() => modalInput.focus(), 0);
    }
    function closeCreateSpecModal() { modalOverlay.classList.add('hidden'); modalState = null; }
    function renderSuggestions() {
        modalSuggestions.innerHTML = '';
        if (!modalState) return;
        if (modalState.filtered.length === 0) {
            const e = document.createElement('div');
            e.className = 'empty';
            e.textContent = modalState.specs.length === 0 ? 'No spec types available' : 'No matches';
            modalSuggestions.appendChild(e);
            return;
        }
        modalState.filtered.forEach((s, i) => {
            const row = document.createElement('div');
            row.className = 'suggestion' + (i === modalState.active ? ' active' : '');
            row.textContent = s;
            row.addEventListener('mousedown', (e) => {
                e.preventDefault();
                modalState.active = i;
                modalInput.value = s;
                modalOk.disabled = false;
                submitCreateSpec();
            });
            modalSuggestions.appendChild(row);
        });
    }
    function filterSuggestions() {
        if (!modalState) return;
        const q = modalInput.value.trim().toLowerCase();
        modalState.filtered = q
            ? modalState.specs.filter((s) => s.toLowerCase().includes(q))
            : modalState.specs.slice();
        modalState.active = 0;
        modalOk.disabled = !modalState.specs.includes(modalInput.value.trim());
        renderSuggestions();
    }
    function submitCreateSpec() {
        if (!modalState) return;
        let pick = modalInput.value.trim();
        if (!modalState.specs.includes(pick) && modalState.filtered.length === 1)
            pick = modalState.filtered[0];
        if (!modalState.specs.includes(pick)) return;
        const url = modalState.url;
        closeCreateSpecModal();
        postMessage({ cmd: 'createSpecConfirmed', url, spec: pick });
    }
    modalInput.addEventListener('input', filterSuggestions);
    modalInput.addEventListener('keydown', (e) => {
        if (!modalState) return;
        if (e.key === 'Escape') { closeCreateSpecModal(); e.preventDefault(); return; }
        if (e.key === 'Enter') { submitCreateSpec(); e.preventDefault(); return; }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            const dir = e.key === 'ArrowDown' ? 1 : -1;
            const n = modalState.filtered.length;
            if (n === 0) return;
            modalState.active = (modalState.active + dir + n) % n;
            modalInput.value = modalState.filtered[modalState.active];
            modalOk.disabled = false;
            renderSuggestions();
            e.preventDefault();
        }
        if (e.key === 'Tab' && modalState.filtered.length > 0) {
            modalInput.value = modalState.filtered[modalState.active];
            modalOk.disabled = false;
            filterSuggestions();
            e.preventDefault();
        }
    });
    modalOk.addEventListener('click', () => submitCreateSpec());
    modalCancel.addEventListener('click', () => closeCreateSpecModal());
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeCreateSpecModal();
    });

    // ----- toolbar -----
    document.getElementById('btn-add').addEventListener('click', () => postMessage({ cmd: 'add' }));
    document.getElementById('btn-reload').addEventListener('click', () => postMessage({ cmd: 'reload' }));
    document.getElementById('btn-configure').addEventListener('click', () => postMessage({ cmd: 'configure' }));
    searchEl.addEventListener('input', () => render());
    searchClear.addEventListener('click', () => { searchEl.value = ''; render(); });
})();
"""
