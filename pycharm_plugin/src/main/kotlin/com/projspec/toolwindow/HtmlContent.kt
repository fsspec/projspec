package com.projspec.toolwindow

/**
 * Generates the HTML/CSS/JS page for the "Project Library" tool window.
 *
 * Port of the VSCode extension's two-pane UI (vsextension/src/panel.ts). The
 * HTML/CSS/JS is reused verbatim wherever possible. Only two things change:
 *
 *   1. `acquireVsCodeApi().postMessage(msg)`  →
 *      `window.__javaBridge.query(JSON.stringify(msg))`
 *      (the JBCefJSQuery is injected from Kotlin after every page load;
 *      see [ProjspecToolWindowPanel.injectBridge]).
 *
 *   2. VSCode `--vscode-*` CSS variables are not resolved by JCEF, so the
 *      stylesheet is prefixed with a small `:root{}` block that binds them
 *      to the Darcula theme colours IntelliJ uses. The rest of the CSS is
 *      untouched.
 *
 * The inbound command vocabulary is identical to the VSCode panel: ready,
 * reload, add, configure, openWith, rescan, createSpec, createSpecConfirmed,
 * removeFromLibrary, make, copyToLocal, revealFile.
 *
 * The outbound messages from Kotlin are delivered to the page by calling
 * `window.__projspecDeliver(msgObj)` via `executeJavaScript`, which
 * re-dispatches to the same handlers that `window.addEventListener('message')`
 * would receive in a real VSCode webview (types: `data`, `loading`,
 * `openCreateSpecModal`).
 */
object HtmlContent {

    fun buildHtml(): String = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Project Library</title>
<style>${THEME_FALLBACKS}${PANEL_CSS}</style>
</head>
<body>
<div id="app">
    <div id="library">
        <div class="toolbar">
            <button id="btn-add">&#x2795; Add</button>
            <button id="btn-reload">&#x1F504; Reload</button>
            <button id="btn-configure">&#x2699;&#xFE0F; Configure</button>
        </div>
        <div class="search">
            <span class="search-icon">&#x1F50D;</span>
            <input type="text" id="search" placeholder="Filter projects..." />
            <button id="search-clear" title="Clear">&#x2716;&#xFE0F;</button>
        </div>
        <div id="projects"></div>
        <div id="spinner" class="hidden">
            <span class="spin">&#x23F3;</span> Loading...
        </div>
    </div>
    <div id="details">
        <div id="details-header">
            <div id="details-title">Details</div>
            <button id="details-toggle" title="Toggle info">&#x1F53C;</button>
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
<script>${PANEL_JS}</script>
</body>
</html>"""

    // -------------------------------------------------------------------------
    // CSS
    // -------------------------------------------------------------------------

    /**
     * Bind the `--vscode-*` CSS variables referenced by the reused stylesheet
     * to Darcula-ish colours so the styling looks right in JCEF.
     */
    private val THEME_FALLBACKS = """
:root {
    --vscode-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    --vscode-editor-font-family: "JetBrains Mono", Consolas, Menlo, monospace;
    --vscode-foreground: #bbbbbb;
    --vscode-editor-background: #2b2b2b;
    --vscode-editorWidget-background: #3c3f41;
    --vscode-editorWidget-foreground: #bbbbbb;
    --vscode-editorWidget-border: #555555;
    --vscode-panel-border: #3c3f41;
    --vscode-focusBorder: #466d94;
    --vscode-descriptionForeground: #8a8a8a;
    --vscode-button-background: #365880;
    --vscode-button-foreground: #ffffff;
    --vscode-button-hoverBackground: #466d94;
    --vscode-button-secondaryBackground: #4c5052;
    --vscode-button-secondaryForeground: #bbbbbb;
    --vscode-input-background: #45494a;
    --vscode-input-foreground: #bbbbbb;
    --vscode-input-border: #646464;
    --vscode-list-hoverBackground: #4c5052;
    --vscode-list-activeSelectionBackground: #365880;
    --vscode-list-activeSelectionForeground: #ffffff;
    --vscode-menu-background: #3c3f41;
    --vscode-menu-foreground: #bbbbbb;
    --vscode-menu-border: #555555;
    --vscode-menu-selectionBackground: #365880;
    --vscode-menu-selectionForeground: #ffffff;
    --vscode-menu-separatorBackground: #555555;
    --vscode-toolbar-hoverBackground: #4c5052;
    --vscode-disabledForeground: #707070;
    --vscode-textLink-foreground: #589df6;
    --vscode-symbolIcon-propertyForeground: #9876aa;
    --vscode-symbolIcon-stringForeground: #6a8759;
    --vscode-symbolIcon-numberForeground: #6897bb;
    --vscode-symbolIcon-keywordForeground: #cc7832;
    --vscode-symbolIcon-enumeratorMemberForeground: #4ec9b0;
}
html, body { height: 100%; }
"""

    /** The VSCode panel stylesheet verbatim. */
    private val PANEL_CSS = """
body { margin: 0; padding: 0; font-family: var(--vscode-font-family); color: var(--vscode-foreground);
       background: var(--vscode-editor-background); }
#app { display: flex; height: 100vh; overflow: hidden; }
#library { width: 40%; min-width: 320px; max-width: 520px; border-right: 1px solid var(--vscode-panel-border);
           display: flex; flex-direction: column; overflow: hidden; }
#details { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.toolbar { display: flex; gap: 6px; padding: 8px; border-bottom: 1px solid var(--vscode-panel-border); }
.toolbar button, .kebab-menu button {
    background: var(--vscode-button-secondaryBackground, var(--vscode-button-background));
    color: var(--vscode-button-secondaryForeground, var(--vscode-button-foreground));
    border: none; padding: 4px 10px; cursor: pointer; font-size: 12px; border-radius: 3px;
}
.toolbar button:hover { background: var(--vscode-button-hoverBackground); }

.search { display: flex; align-items: center; gap: 6px; padding: 6px 8px;
          border-bottom: 1px solid var(--vscode-panel-border); }
.search input { flex: 1; background: var(--vscode-input-background); color: var(--vscode-input-foreground);
                border: 1px solid var(--vscode-input-border, transparent); padding: 4px 8px; font-size: 12px;
                border-radius: 2px; }
.search button { background: transparent; color: var(--vscode-descriptionForeground);
                 border: none; cursor: pointer; padding: 2px 4px; }
.search button:hover { color: var(--vscode-foreground); }

#projects { flex: 1; overflow-y: auto; padding: 6px; }
#spinner { text-align: center; padding: 16px; color: var(--vscode-descriptionForeground); }
#spinner .spin { display: inline-block; animation: spin 1.2s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.hidden { display: none !important; }

.project {
    border: 1px solid var(--vscode-panel-border);
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 6px;
    cursor: pointer;
    position: relative;
    background: var(--vscode-editorWidget-background);
}
.project:hover { background: var(--vscode-list-hoverBackground); }
.project.active {
    border-color: var(--vscode-focusBorder);
    background: var(--vscode-list-activeSelectionBackground, var(--vscode-list-hoverBackground));
}
.project .title { font-weight: bold; margin-right: 24px; }
.project .url { font-size: 11px; color: var(--vscode-descriptionForeground); word-break: break-all; margin-top: 2px; }
.project .storage-opts { font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 2px; font-style: italic; }
.project .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }

.chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: #c5e0c1;
    color: #222;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    cursor: pointer;
    border: 1px solid transparent;
    user-select: none;
}
.chip:hover { filter: brightness(0.95); }
.chip.active { border-color: var(--vscode-focusBorder); box-shadow: 0 0 0 1px var(--vscode-focusBorder); }

.kebab {
    position: absolute; top: 6px; right: 6px;
    background: transparent; border: none; color: var(--vscode-foreground);
    cursor: pointer; padding: 2px 6px; border-radius: 3px;
}
.kebab:hover { background: var(--vscode-toolbar-hoverBackground); }
.kebab-menu {
    position: absolute; right: 6px; top: 28px;
    background: var(--vscode-menu-background, var(--vscode-editorWidget-background));
    color: var(--vscode-menu-foreground, var(--vscode-foreground));
    border: 1px solid var(--vscode-menu-border, var(--vscode-panel-border));
    border-radius: 3px; padding: 4px 0; z-index: 10;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3); min-width: 180px;
}
.kebab-menu .menu-item { padding: 4px 12px; cursor: pointer; font-size: 12px; white-space: nowrap; }
.kebab-menu .menu-item:hover { background: var(--vscode-menu-selectionBackground, var(--vscode-list-hoverBackground));
                               color: var(--vscode-menu-selectionForeground, var(--vscode-foreground)); }
.kebab-menu .menu-item.disabled { color: var(--vscode-disabledForeground); cursor: default; }
.kebab-menu .menu-item.disabled:hover { background: transparent; }
.kebab-menu .menu-sep {
    height: 1px; margin: 4px 0;
    background: var(--vscode-menu-separatorBackground, var(--vscode-panel-border));
}

/* Details panel */
#details-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px;
                  border-bottom: 1px solid var(--vscode-panel-border); }
#details-title { font-weight: bold; font-size: 14px; flex: 1; }
#details-toggle { background: transparent; border: none; color: var(--vscode-foreground); cursor: pointer;
                  padding: 2px 6px; }
#details-info { padding: 8px 12px; border-bottom: 1px solid var(--vscode-panel-border);
                color: var(--vscode-descriptionForeground); font-size: 12px; }
#details-info a { color: var(--vscode-textLink-foreground); }
#details-info.hidden { display: none; }
#details-info.collapsed { display: none; }
#details-list { flex: 1; overflow-y: auto; padding: 8px 12px; }

.item-widget {
    position: relative;
    border: 1px solid var(--vscode-panel-border);
    border-radius: 4px;
    margin-bottom: 8px;
    padding: 8px 10px;
    background: var(--vscode-editorWidget-background);
}
.item-widget.kind-content { border-color: #4ca97a; box-shadow: 0 0 0 1px rgba(76,169,122,0.15); }
.item-widget.kind-artifact { border-color: #c66060; box-shadow: 0 0 0 1px rgba(198,96,96,0.15); }
.item-widget .widget-html { margin-top: 6px; font-size: 12px; line-height: 1.4; }
.item-widget .widget-html img { max-width: 100%; height: auto; }
.item-widget .widget-html a { color: var(--vscode-textLink-foreground); }
.item-widget .widget-html table { border-collapse: collapse; }
.item-widget .widget-html th, .item-widget .widget-html td {
    border: 1px solid var(--vscode-panel-border); padding: 2px 6px;
}
.item-widget .widget-title { font-weight: bold; font-size: 13px; }
.item-widget .widget-subtitle { font-size: 11px; color: var(--vscode-descriptionForeground); }
.item-widget .widget-actions { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px;
                               opacity: 0; transition: opacity 0.1s; }
.item-widget:hover .widget-actions { opacity: 1; }
.item-widget .widget-actions button {
    background: transparent; border: none; color: var(--vscode-foreground);
    cursor: pointer; padding: 2px 6px; border-radius: 3px;
}
.item-widget .widget-actions button:hover { background: var(--vscode-toolbar-hoverBackground); }

.tree { font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; margin-top: 6px; }
.tree .node { padding-left: 14px; position: relative; }
.tree .node.collapsible > .label { cursor: pointer; }
.tree .node.collapsible > .label::before {
    content: '\25BE'; position: absolute; left: 0; font-size: 10px; top: 2px;
}
.tree .node.collapsible.collapsed > .label::before { content: '\25B8'; }
.tree .node.collapsible.collapsed > .children { display: none; }
.tree .key { color: var(--vscode-symbolIcon-propertyForeground, var(--vscode-foreground)); }
.tree .value.str { color: var(--vscode-symbolIcon-stringForeground, #ce9178); }
.tree .value.num { color: var(--vscode-symbolIcon-numberForeground, #b5cea8); }
.tree .value.bool, .tree .value.null { color: var(--vscode-symbolIcon-keywordForeground, #569cd6); }
.tree .value.enum { color: var(--vscode-symbolIcon-enumeratorMemberForeground, #4ec9b0); font-weight: 600; }
.tree .value.empty { color: var(--vscode-descriptionForeground); font-style: italic; }

/* YAML-style list/map items */
.tree.yaml .yaml-item { position: relative; padding-left: 0; }
.tree.yaml .yaml-item.list-item { display: flex; align-items: flex-start; flex-wrap: wrap; }
.tree.yaml .yaml-item .marker { color: var(--vscode-descriptionForeground); user-select: none;
                                 padding-right: 2px; }
.tree.yaml .yaml-item.collapsible > .marker,
.tree.yaml .yaml-item.collapsible > .label { cursor: pointer; }
.tree.yaml .yaml-item.collapsible > .marker::after,
.tree.yaml .yaml-item.collapsible > .label::after {
    content: ' \25BE'; font-size: 9px; color: var(--vscode-descriptionForeground);
}
.tree.yaml .yaml-item.collapsible.collapsed > .marker::after,
.tree.yaml .yaml-item.collapsible.collapsed > .label::after { content: ' \25B8'; }
.tree.yaml .yaml-item.collapsible.collapsed > .children { display: none; }
.tree.yaml .yaml-item .body.empty { display: none; }
.tree.yaml .yaml-item > .children { padding-left: 16px; width: 100%; }
.tree.yaml .yaml-item.list-item > .children { margin-top: 0; }

#popup {
    position: fixed; background: var(--vscode-editorWidget-background);
    color: var(--vscode-editorWidget-foreground, var(--vscode-foreground));
    border: 1px solid var(--vscode-editorWidget-border, var(--vscode-panel-border));
    padding: 8px 10px; border-radius: 4px; max-width: 360px; z-index: 1000;
    box-shadow: 0 4px 10px rgba(0,0,0,0.4); font-size: 12px;
}
#popup a { color: var(--vscode-textLink-foreground); }

/* Create-spec modal */
#modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center;
    z-index: 2000;
}
#modal {
    background: var(--vscode-editorWidget-background);
    color: var(--vscode-editorWidget-foreground, var(--vscode-foreground));
    border: 1px solid var(--vscode-editorWidget-border, var(--vscode-panel-border));
    border-radius: 6px;
    min-width: 360px; max-width: 80%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    display: flex; flex-direction: column;
}
#modal-title {
    padding: 10px 14px; font-weight: bold; font-size: 14px;
    border-bottom: 1px solid var(--vscode-panel-border);
}
#modal-body { padding: 12px 14px; }
#modal-body label { display: block; font-size: 12px; margin-bottom: 4px;
                    color: var(--vscode-descriptionForeground); }
#modal-input {
    width: 100%; box-sizing: border-box;
    background: var(--vscode-input-background); color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border, var(--vscode-focusBorder, transparent));
    padding: 6px 8px; font-size: 13px; border-radius: 3px;
    outline: none;
}
#modal-input:focus { border-color: var(--vscode-focusBorder); }
#modal-suggestions {
    margin-top: 6px; max-height: 220px; overflow-y: auto;
    border: 1px solid var(--vscode-panel-border); border-radius: 3px;
    font-size: 12px; background: var(--vscode-input-background);
}
#modal-suggestions .suggestion { padding: 4px 8px; cursor: pointer; }
#modal-suggestions .suggestion:hover,
#modal-suggestions .suggestion.active {
    background: var(--vscode-list-activeSelectionBackground, var(--vscode-list-hoverBackground));
    color: var(--vscode-list-activeSelectionForeground, var(--vscode-foreground));
}
#modal-suggestions .empty {
    padding: 4px 8px; color: var(--vscode-descriptionForeground); font-style: italic;
}
#modal-actions {
    display: flex; justify-content: flex-end; gap: 6px;
    padding: 10px 14px; border-top: 1px solid var(--vscode-panel-border);
}
#modal-actions button {
    border: none; cursor: pointer; padding: 6px 14px; font-size: 12px;
    border-radius: 3px;
}
#modal-actions button.primary {
    background: var(--vscode-button-background); color: var(--vscode-button-foreground);
}
#modal-actions button.primary:hover:not(:disabled) { background: var(--vscode-button-hoverBackground); }
#modal-actions button.primary:disabled { opacity: 0.5; cursor: default; }
#modal-actions button.secondary {
    background: var(--vscode-button-secondaryBackground, transparent);
    color: var(--vscode-button-secondaryForeground, var(--vscode-foreground));
    border: 1px solid var(--vscode-panel-border);
}
#modal-actions button.secondary:hover { background: var(--vscode-toolbar-hoverBackground); }
"""

    // -------------------------------------------------------------------------
    // JS
    // -------------------------------------------------------------------------

    /**
     * Panel JS reused verbatim from vsextension/src/panel.ts (PANEL_JS).
     *
     * The only changes:
     *   - the `vscode` shim at the top calls `window.__javaBridge.query(...)`
     *     (set up from Kotlin) instead of `acquireVsCodeApi()`.
     *   - outbound messages from Kotlin call `window.__projspecDeliver(msg)`
     *     which simply calls the same handler that `message` events did,
     *     because JCEF doesn't deliver browser `postMessage` events to an
     *     iframe-less page the way VSCode does.
     *
     * Uses a Kotlin raw string `""" ... """` so JS escapes survive unaltered;
     * the sentinel `${'$'}` is used wherever a `$` must remain literal in the
     * output (template-literal placeholders inside the JS).
     */
    private val PANEL_JS = """
(function() {
    // ------------------------------------------------------------------
    // Bridge: Java ↔ JS.  The Kotlin side injects a `window.__javaBridge`
    // object via JBCefJSQuery.inject(), but that only runs after the page
    // has finished loading — whereas this IIFE runs DURING load.  So we
    // expose a `vscode.postMessage()` that queues outbound messages while
    // the bridge is absent, then flushes them as soon as Kotlin calls
    // `window.__projspecBridgeReady()`.
    // ------------------------------------------------------------------
    const outboundQueue = [];
    function sendNow(msg) {
        try { window.__javaBridge.query(JSON.stringify(msg)); }
        catch (e) { /* swallow: bridge broken */ }
    }
    const vscode = {
        postMessage: function(msg) {
            if (window.__javaBridge && window.__javaBridge.query) {
                sendNow(msg);
            } else {
                outboundQueue.push(msg);
            }
        }
    };
    // Kotlin calls this once `window.__javaBridge` has been installed.
    window.__projspecBridgeReady = function() {
        while (outboundQueue.length > 0) { sendNow(outboundQueue.shift()); }
    };
    // Kotlin delivers host→webview messages by calling this function.
    window.__projspecDeliver = function(msg) { handleHostMessage(msg); };
    // If the bridge was injected before this IIFE ran (e.g. because
    // onLoadEnd fired very quickly), flush immediately.
    if (window.__javaBridge && window.__javaBridge.query) {
        window.__projspecBridgeReady();
    }

    let info = null;
    let enums = {};
    let library = {};
    // selection state: { url: string, kind: 'contents'|'artifacts'|'spec', specName?: string }
    let selection = null;

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

    // ----- subroutines -----
    function basename(url) {
        try {
            const stripped = url.replace(/\/+${'$'}/, '');
            const idx = stripped.lastIndexOf('/');
            return idx >= 0 ? stripped.slice(idx + 1) : stripped;
        } catch (_) { return url; }
    }
    function specDisplayName(snake) { return snake; }
    function iconForSpec(snake) {
        const entry = info && info.specs && info.specs[snake];
        return (entry && entry.icon) || '\u{1F9E9}'; // puzzle piece
    }
    function iconForContent(snake) {
        const entry = info && info.content && info.content[snake];
        return (entry && entry.icon) || '\u{1F4C4}'; // page
    }
    function iconForArtifact(snake) {
        const entry = info && info.artifact && info.artifact[snake];
        return (entry && entry.icon) || '\u{1F4E6}'; // box
    }

    // ----- rendering -----
    const projectsEl = document.getElementById('projects');
    const spinnerEl = document.getElementById('spinner');
    const searchEl = document.getElementById('search');
    const searchClear = document.getElementById('search-clear');

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
            e.style.color = 'var(--vscode-descriptionForeground)';
            e.style.textAlign = 'center';
            e.textContent = urls.length === 0 ? 'Library is empty. Click "Add" to scan a directory.' : 'No projects match the filter.';
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
        if (Object.keys(contents).length > 0) {
            chips.appendChild(makeChip('Contents <' + Object.keys(contents).length + '>', url, 'contents', null, null));
        }
        if (Object.keys(artifacts).length > 0) {
            chips.appendChild(makeChip('Artifacts <' + Object.keys(artifacts).length + '>', url, 'artifacts', null, null));
        }
        for (const specName of Object.keys(project.specs || {})) {
            chips.appendChild(makeChip(specDisplayName(specName), url, 'spec', specName, iconForSpec(specName)));
        }
        wrap.appendChild(chips);

        // Kebab menu
        const kebabBtn = document.createElement('button');
        kebabBtn.className = 'kebab';
        kebabBtn.title = 'More actions';
        kebabBtn.textContent = '\u22EE';
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
        if (icon) {
            chip.innerHTML = '<span class="chip-icon">' + escapeHtml(icon) + '</span><span>' + escapeHtml(label) + '</span>';
        } else {
            chip.textContent = label;
        }
        chip.addEventListener('click', (ev) => {
            ev.stopPropagation();
            selection = { url: url, kind: kind, specName: specName };
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

    // Kebab handling
    let openKebab = null;
    function toggleKebab(projectEl, url) {
        if (openKebab && openKebab.el === projectEl) { closeKebab(); return; }
        closeKebab();
        const menu = document.createElement('div');
        menu.className = 'kebab-menu';
        const isLocal = url.startsWith('file://');
        if (isLocal) {
            addItem(menu, 'Open with VSCode', () => vscode.postMessage({ cmd: 'openWith', tool: 'vscode', url: url }));
            addItem(menu, 'Open with system filebrowser', () => vscode.postMessage({ cmd: 'openWith', tool: 'filebrowser', url: url }));
            addItem(menu, 'Open with PyCharm', () => vscode.postMessage({ cmd: 'openWith', tool: 'pycharm', url: url }));
            addItem(menu, 'Open with jupyter', () => vscode.postMessage({ cmd: 'openWith', tool: 'jupyter', url: url }));
            addSeparator(menu);
            addItem(menu, 'Rescan', () => vscode.postMessage({ cmd: 'rescan', url: url }));
            addItem(menu, 'Create spec', () => vscode.postMessage({ cmd: 'createSpec', url: url }));
            addItem(menu, 'Remove from library', () => vscode.postMessage({ cmd: 'removeFromLibrary', url: url }));
        } else {
            const ctl = addItem(menu, 'Copy to local', () => vscode.postMessage({ cmd: 'copyToLocal', url: url }));
            ctl.classList.add('disabled');
            addItem(menu, 'Rescan', () => vscode.postMessage({ cmd: 'rescan', url: url }));
            addItem(menu, 'Remove from library', () => vscode.postMessage({ cmd: 'removeFromLibrary', url: url }));
        }
        projectEl.appendChild(menu);
        openKebab = { el: projectEl, menu: menu };
        setTimeout(() => document.addEventListener('click', onDocClick, { once: true }), 0);
    }
    function addItem(menu, label, onClick) {
        const mi = document.createElement('div');
        mi.className = 'menu-item';
        mi.textContent = label;
        mi.addEventListener('click', (e) => { e.stopPropagation(); if (!mi.classList.contains('disabled')) { onClick(); closeKebab(); } });
        menu.appendChild(mi);
        return mi;
    }
    function addSeparator(menu) {
        const sep = document.createElement('div');
        sep.className = 'menu-sep';
        menu.appendChild(sep);
    }
    function closeKebab() {
        if (openKebab) {
            openKebab.menu.remove();
            openKebab = null;
        }
    }
    function onDocClick() { closeKebab(); }

    // ----- details panel -----
    const detailsTitle = document.getElementById('details-title');
    const detailsInfo = document.getElementById('details-info');
    const detailsList = document.getElementById('details-list');
    const detailsToggle = document.getElementById('details-toggle');

    detailsToggle.addEventListener('click', () => {
        detailsInfo.classList.toggle('collapsed');
    });

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
                for (const e of entry) {
                    detailsList.appendChild(makeItemWidget(typeName, null, e, kind, showMake, specName));
                }
            } else if (entry && typeof entry === 'object' && 'klass' in entry) {
                detailsList.appendChild(makeItemWidget(typeName, null, entry, kind, showMake, specName));
            } else if (entry && typeof entry === 'object') {
                for (const name of Object.keys(entry)) {
                    detailsList.appendChild(makeItemWidget(typeName, name, entry[name], kind, showMake, specName));
                }
            } else {
                const obj = {}; obj[typeName] = entry;
                detailsList.appendChild(makePlainWidget(obj));
            }
        }
    }

    function hasKlass(v) {
        if (!v || typeof v !== 'object') return false;
        if (!Array.isArray(v) && 'klass' in v) return true;
        if (Array.isArray(v)) {
            for (const e of v) if (hasKlass(e)) return true;
            return false;
        }
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
        title.innerHTML = '<span class="widget-icon">' + escapeHtml(iconName) + '</span> ' + escapeHtml(klass) + (name ? ' <span class="widget-subtitle">- ' + escapeHtml(name) + '</span>' : '');
        w.appendChild(title);

        const actions = document.createElement('div');
        actions.className = 'widget-actions';

        const fn = (data && typeof data === 'object') ? data.fn : undefined;
        if (kind === 'artifact' && typeof fn === 'string' && fn.length > 0 && isLocalPath(fn)) {
            const rv = document.createElement('button');
            rv.title = 'Reveal ' + fn + ' in project view';
            rv.textContent = '\u27A1\uFE0F';
            rv.addEventListener('click', (e) => {
                e.stopPropagation();
                vscode.postMessage({ cmd: 'revealFile', fn: fn });
            });
            actions.appendChild(rv);
        }

        if (showMake) {
            const mk = document.createElement('button');
            mk.title = 'Make';
            mk.textContent = '\u25B6\uFE0F';
            mk.addEventListener('click', (e) => {
                e.stopPropagation();
                vscode.postMessage({
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
        ib.textContent = '\u2139\uFE0F';
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
            if (tag === 'script' || tag === 'iframe' || tag === 'object' || tag === 'embed') {
                toRemove.push(n);
            } else {
                for (const attr of Array.from(n.attributes)) {
                    const an = attr.name.toLowerCase();
                    if (an.startsWith('on')) { n.removeAttribute(attr.name); continue; }
                    if ((an === 'href' || an === 'src') && /^\s*javascript:/i.test(attr.value)) {
                        n.removeAttribute(attr.name);
                    }
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
        for (const k of Object.keys(obj)) {
            if (k === 'klass') continue;
            out[k] = obj[k];
        }
        return out;
    }

    // ----- YAML-style rendering -----
    function renderYaml(data) {
        const frag = document.createDocumentFragment();
        if (Array.isArray(data)) {
            if (data.length === 0) {
                frag.appendChild(textNode('[]', 'value empty'));
                return frag;
            }
            for (const item of data) {
                frag.appendChild(yamlListItem(item));
            }
            return frag;
        }
        if (data && typeof data === 'object') {
            const keys = Object.keys(data);
            if (keys.length === 0) {
                frag.appendChild(textNode('{}', 'value empty'));
                return frag;
            }
            for (const k of keys) {
                frag.appendChild(yamlMapItem(k, data[k]));
            }
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
            node.appendChild(marker);
            node.appendChild(body);
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
            marker.addEventListener('click', (e) => { e.stopPropagation(); node.classList.toggle('collapsed'); });
            return node;
        }
        body.appendChild(primitiveSpan(value));
        node.appendChild(marker);
        node.appendChild(body);
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
            label.addEventListener('click', (e) => { e.stopPropagation(); node.classList.toggle('collapsed'); });
            return node;
        }
        label.innerHTML = '<span class="key">' + escapeHtml(key) + '</span>: ';
        label.appendChild(primitiveSpan(value));
        node.appendChild(label);
        return node;
    }

    function isEnum(v) {
        return v && typeof v === 'object' && !Array.isArray(v)
            && Array.isArray(v.klass) && v.klass[0] === 'enum'
            && ('value' in v);
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
        if (typeof v === 'string') {
            s.classList.add('str');
            s.textContent = v;
        } else if (typeof v === 'number') {
            s.classList.add('num');
            s.textContent = String(v);
        } else if (typeof v === 'boolean') {
            s.classList.add('bool');
            s.textContent = String(v);
        } else if (v === null || v === undefined) {
            s.classList.add('null');
            s.textContent = 'null';
        } else {
            s.textContent = String(v);
        }
        return s;
    }

    function textNode(text, cls) {
        const s = document.createElement('span');
        if (cls) s.className = cls;
        s.textContent = text;
        return s;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function isLocalPath(p) {
        if (p.startsWith('file://')) return true;
        return !/^[a-z][a-z0-9+.-]*:\/\//i.test(p);
    }

    // ----- info popup -----
    const popup = document.getElementById('popup');
    function showInfoPopup(klass, kind, mx, my) {
        const map = kind === 'content' ? (info && info.content) : (info && info.artifact);
        const entry = map && map[klass];
        if (!entry) {
            popup.innerHTML = '<em>No info for ' + escapeHtml(klass) + '</em>';
        } else {
            popup.innerHTML = '<div style="font-weight:bold;margin-bottom:4px;">' + escapeHtml(klass) + '</div>' +
                              '<div style="white-space:pre-wrap;">' + escapeHtml(entry.doc || '') + '</div>';
        }
        popup.classList.remove('hidden');
        popup.style.left = '-9999px';
        popup.style.top = '-9999px';
        requestAnimationFrame(() => {
            const w = popup.offsetWidth;
            const h = popup.offsetHeight;
            let x = mx - w - 8;
            let y = my - 8;
            if (x < 4) x = 4;
            if (y + h > window.innerHeight - 4) y = window.innerHeight - h - 4;
            if (y < 4) y = 4;
            popup.style.left = x + 'px';
            popup.style.top = y + 'px';
        });
        setTimeout(() => {
            document.addEventListener('click', hideInfoPopup, { once: true });
        }, 0);
    }
    function hideInfoPopup() { popup.classList.add('hidden'); }

    // ----- create-spec modal -----
    const modalOverlay = document.getElementById('modal-overlay');
    const modalInput = document.getElementById('modal-input');
    const modalSuggestions = document.getElementById('modal-suggestions');
    const modalOk = document.getElementById('modal-ok');
    const modalCancel = document.getElementById('modal-cancel');
    const modalEl = document.getElementById('modal');
    let modalState = null; // { url, specs, filtered, active }

    function openCreateSpecModal(url, specs) {
        modalState = { url: url, specs: specs.slice(), filtered: specs.slice(), active: 0 };
        modalInput.value = '';
        modalOk.disabled = true;
        renderSuggestions();
        modalOverlay.classList.remove('hidden');
        setTimeout(() => modalInput.focus(), 0);
    }
    function closeCreateSpecModal() {
        modalOverlay.classList.add('hidden');
        modalState = null;
    }
    function renderSuggestions() {
        modalSuggestions.innerHTML = '';
        if (!modalState) return;
        if (modalState.filtered.length === 0) {
            const e = document.createElement('div');
            e.className = 'empty';
            e.textContent = modalState.specs.length === 0
                ? 'No spec types available'
                : 'No matches';
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
        if (!modalState.specs.includes(pick) && modalState.filtered.length === 1) {
            pick = modalState.filtered[0];
        }
        if (!modalState.specs.includes(pick)) return;
        const url = modalState.url;
        closeCreateSpecModal();
        vscode.postMessage({ cmd: 'createSpecConfirmed', url: url, spec: pick });
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
    document.getElementById('btn-add').addEventListener('click', () => vscode.postMessage({ cmd: 'add' }));
    document.getElementById('btn-reload').addEventListener('click', () => vscode.postMessage({ cmd: 'reload' }));
    document.getElementById('btn-configure').addEventListener('click', () => vscode.postMessage({ cmd: 'configure' }));
    searchEl.addEventListener('input', () => render());
    searchClear.addEventListener('click', () => { searchEl.value = ''; render(); });

    // ----- host → webview dispatch -----
    function handleHostMessage(msg) {
        if (!msg) return;
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

    vscode.postMessage({ cmd: 'ready' });
})();
"""
}
