/* projspec filebrowser panel — transport-agnostic.
 *
 * Like panel.js this script requires the host to set
 *   window.projspecFbTransport = { send(msg), onReady(dispatch) }
 * BEFORE this script runs.  The transport bridges JS↔host for all
 * filebrowser operations (browse, inspect, createFile, …).
 *
 * Optionally set window.projspecFbRoot to scope DOM queries to a
 * subtree (needed when the panel is embedded alongside other content).
 *
 * Hosts that embed the library panel inside the scan pane must also set
 * window.projspecFbPanelBootstrap = bootstrapFn (called once to
 * initialise the embedded panel.js instance for directory scan results).
 */
(function() {
    // ── Transport -----------------------------------------------------------
    const _transport = window.projspecFbTransport || {
        send: (msg) => { console.warn('projspec-fb: no transport configured', msg); },
        onReady: (dispatch) => { window.__projspecFbDeliver = dispatch; },
    };

    // Root scoping (mirrors panel.js pattern)
    const _fbRoot = window.projspecFbRoot || document;
    function $fbId(id) {
        if (_fbRoot === document) return document.getElementById(id);
        return _fbRoot.querySelector('#' + CSS.escape(id));
    }

    // Outbound (JS → host)
    const vscode = { postMessage: (msg) => _transport.send(msg) };

    // Show any uncaught JS errors as a red banner
    window.onerror = function(msg, src, line, col, err) {
        var d = document.createElement('div');
        d.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:10px;background:#c00;color:#fff;font-family:monospace;font-size:12px;z-index:9999;white-space:pre-wrap;';
        d.textContent = 'FB error: ' + msg + ' (' + src + ':' + line + ')';
        document.body.appendChild(d);
    };

    // ── debug log ─────────────────────────────────────────────────────────
    function dbg(msg) {
        console.log('[fb] ' + msg);
        _transport.send({ cmd: 'log', msg: msg });
    }
    dbg('script started');

    // ── state ──────────────────────────────────────────────────────────────
    let bookmarks = [];
    let protocols = [];
    var libraryUrls = new Set();  // canonical URLs of entries in the project library
    var selectedIsFile = false;   // true when the current selection is a file (not a dir)
    let currentUrl = '';
    let currentSo  = '';
    let history    = [];
    let histIdx    = -1;
    let selected   = null;
    let newentryMode = 'file';
    let showHidden = false;       // off by default — hides dotfile-style entries

    // Multi-select state: url -> {type, so}. `selected` (above) is kept in
    // sync as a convenience derived value: non-null only when exactly one
    // entry is selected (used by the single-item-only info panel actions:
    // Open, +Library, Bookmark, Rename).
    let selectedSet = new Map();
    let anchorUrl = null;  // last click target, used as the shift-range anchor

    // Copy/cut/paste clipboard — { items: [{url, so, type}], mode: 'copy'|'cut' } or null.
    // Always a list, even for a single copied/cut item.
    let clipboard = null;
    // Context-menu target — { targets: [{url, so, type}], isBackground } or null.
    let ctxTarget = null;
    // Pending paste awaiting large-copy confirmation —
    // { items: [{src, srcSo}], dstDir, dstSo, mode } or null.
    let pendingPaste = null;
    // Shared rename target (set from either the toolbar button or the context menu).
    // Rename only ever applies to a single item.
    let renameTarget = null;

    // ── DOM refs ───────────────────────────────────────────────────────────
    // NOTE: #fb-entries is the scrollable entry list. #fb-empty and
    // #fb-error are siblings of #fb-entries inside #fb-file-list and must
    // NEVER be cleared by setting innerHTML on their parent.
    const entriesEl   = $fbId('fb-entries');
    const emptyEl     = $fbId('fb-empty');
    const errorEl     = $fbId('fb-error');
    const urlInput    = $fbId('fb-url-input');
    const breadcrumb  = $fbId('fb-breadcrumb');
    const spinner     = $fbId('fb-spinner');
    const infoTitle   = $fbId('fb-info-title');
    const infoActions = $fbId('fb-info-actions');
    const infoMeta    = $fbId('fb-info-meta');
    const infoPreview = $fbId('fb-info-preview');
    const scanPane      = $fbId('fb-scan-pane');
    const scanStatus    = $fbId('fb-scan-status');
    const scanPanelRoot = $fbId('fb-scan-panel-root');
    const fileContent   = $fbId('fb-file-content');
    const bmPanel     = $fbId('bm-panel');
    const bmList      = $fbId('bm-list');
    const soOverlay   = $fbId('so-overlay');
    const soInput     = $fbId('so-input');
    const neOverlay   = $fbId('newentry-overlay');
    const neTitle     = $fbId('newentry-title');
    const neInput     = $fbId('newentry-name');
    const renOverlay  = $fbId('rename-overlay');
    const renInput    = $fbId('rename-input');
    const ctxMenu       = $fbId('fb-ctxmenu');
    const pasteConfirmOverlay = $fbId('paste-confirm-overlay');
    const pasteConfirmMsg    = $fbId('paste-confirm-msg');

    // Verify critical elements exist
    const missing = ['fb-entries','fb-empty','fb-error','fb-url-input','fb-breadcrumb',
                     'fb-spinner','fb-info-title','fb-info-actions'].filter(id => !$fbId(id));
    if (missing.length) { dbg('ERROR: missing elements: ' + missing.join(', ')); }
    else { dbg('all DOM elements found'); }

    // ── utilities ──────────────────────────────────────────────────────────
    function basename(url) {
        const s = (url || '').replace(/\/+$/, '');
        const i = s.lastIndexOf('/');
        return i >= 0 ? s.slice(i + 1) : s;
    }
    // "Hidden" follows the standard dotfile convention (name starts with
    // '.'); fsspec/browse() doesn't expose a platform hidden-attribute, so
    // this is the same simple, universal rule every Unix-like file manager
    // uses.
    function isHiddenEntry(entry) {
        var name = entry.basename || basename(entry.name || '');
        return name.charAt(0) === '.';
    }
    function visibleEntries(entries) {
        return showHidden ? entries : entries.filter(function(e) { return !isHiddenEntry(e); });
    }
    function parentUrl(url) {
        const s = (url || '').replace(/\/+$/, '');
        const protoEnd = s.indexOf('://');
        if (protoEnd >= 0) {
            const pathPart = s.slice(protoEnd + 3);
            const slash = pathPart.lastIndexOf('/');
            if (slash <= 0) return s.slice(0, protoEnd + 3) || s;
            return s.slice(0, protoEnd + 3 + slash);
        }
        const slash = s.lastIndexOf('/');
        if (slash <= 0) return '/';
        return s.slice(0, slash);
    }
    function fmtSize(bytes) {
        if (bytes == null) return '';
        const u = ['B','KB','MB','GB','TB'];
        let n = parseFloat(bytes);
        for (let i = 0; i < u.length; i++) {
            if (n < 1024 || i === u.length - 1) return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + u[i];
            n /= 1024;
        }
    }
    function fmtDate(ts) {
        if (!ts) return '';
        const d = new Date(parseFloat(ts) * 1000);
        return d.toLocaleString();
    }
    function escHtml(s) {
        return String(s || '').replace(/[&<>"']/g,
            c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function fileIcon(entry, inLibrary) {
        if (entry.type === 'directory') return inLibrary ? '\uD83D\uDDC2\uFE0F' : '\uD83D\uDCC1'; // 🗂️ or 📁
        const name = (entry.basename || entry.name || '').toLowerCase();
        if (/\.(py|pyx|pyi)$/.test(name))                   return '\uD83D\uDC0D'; // snake
        if (/\.(js|ts|jsx|tsx)$/.test(name))                 return '\uD83D\uDCDC'; // scroll
        if (/\.(json|yaml|yml|toml|ini|cfg)$/.test(name))    return '\u2699\uFE0F'; // gear
        if (/\.(md|rst|txt|org)$/.test(name))                return '\uD83D\uDCC4'; // page
        if (/\.(csv|tsv|parquet|hdf5?|nc|zarr|feather)$/.test(name)) return '\uD83D\uDCCA'; // chart
        if (/\.(png|jpg|jpeg|gif|svg|webp|bmp|tiff?)$/.test(name))   return '\uD83D\uDDBC\uFE0F'; // picture
        if (/\.(zip|tar|gz|bz2|xz|7z|rar)$/.test(name))     return '\uD83D\uDCE6'; // package
        if (/\.(sh|bash|zsh|fish|ps1|bat|cmd)$/.test(name)) return '\uD83D\uDCBB'; // computer
        return '\uD83D\uDCC4'; // page
    }

    // ── browse result ──────────────────────────────────────────────────────
    // ── tree rendering ─────────────────────────────────────────────────────

    // Sort state
    var sortCol = 'name';   // 'name' | 'size' | 'mtime'
    var sortAsc = true;
    // Last browse entries (root level) — kept for re-sort without re-fetch
    var lastBrowseEntries = [];

    function sortEntries(entries) {
        // Stable sort: directories always before files, then by chosen column
        function key(e) {
            if (sortCol === 'size')  return e.size  == null ? -1 : e.size;
            if (sortCol === 'mtime') return e.last_modified == null ? 0 : parseFloat(e.last_modified);
            // name: case-insensitive
            return (e.basename || basename(e.name || '')).toLowerCase();
        }
        return entries.slice().sort(function(a, b) {
            var aDir = a.type === 'directory' ? 0 : 1;
            var bDir = b.type === 'directory' ? 0 : 1;
            if (aDir !== bDir) return aDir - bDir;  // dirs before files always
            var ak = key(a), bk = key(b);
            var cmp = ak < bk ? -1 : ak > bk ? 1 : 0;
            return sortAsc ? cmp : -cmp;
        });
    }

    function updateSortHeaders() {
        (_fbRoot === document ? document : _fbRoot).querySelectorAll('.fb-col-hdr').forEach(function(el) {
            var col = el.dataset.col;
            var arrow = el.querySelector('.fb-sort-arrow');
            if (col === sortCol) {
                el.classList.add('active');
                if (arrow) arrow.textContent = sortAsc ? '\u25B4' : '\u25BE'; // ▴ ▾
            } else {
                el.classList.remove('active');
                if (arrow) arrow.textContent = '';
            }
        });
    }

    // Re-renders the root-level (#fb-entries) listing from the cached raw
    // `lastBrowseEntries` — applying the current sort and show-hidden
    // filter without a network round-trip. Used after a sort-column
    // change, after toggling "Show hidden", and by renderBrowse() itself.
    // Any expanded subdirectories collapse (treeNodes is reset); the
    // filter applies to their contents too the next time they're expanded.
    function renderRootEntries() {
        treeNodes = {};
        entriesEl.innerHTML = '';
        emptyEl.classList.add('hidden');
        var visible = visibleEntries(lastBrowseEntries);
        if (lastBrowseEntries.length === 0) {
            emptyEl.textContent = 'Directory is empty.';
            emptyEl.classList.remove('hidden');
            return;
        }
        if (visible.length === 0) {
            emptyEl.textContent = 'All items are hidden.';
            emptyEl.classList.remove('hidden');
            return;
        }
        var sorted = sortEntries(visible);
        for (var i = 0; i < sorted.length; i++) {
            entriesEl.appendChild(makeEntryRow(sorted[i], 0));
        }
    }

    // Wire up column header clicks
    (_fbRoot === document ? document : _fbRoot).querySelectorAll('.fb-col-hdr').forEach(function(el) {
        el.addEventListener('click', function() {
            var col = el.dataset.col;
            if (col === sortCol) {
                sortAsc = !sortAsc;
            } else {
                sortCol = col;
                sortAsc = col === 'name';  // name defaults asc, size/mtime default desc
            }
            updateSortHeaders();
            // Re-render root entries with new sort (no network call)
            renderRootEntries();
        });
    });
    updateSortHeaders();

    // Map from directory URL -> child container element (for expand/collapse)
    var treeNodes = {};

    function makeEntryRow(entry, depth) {
        var isDir = entry.type === 'directory';
        var url   = entry.name;

        // Outer wrapper: row + (for dirs) a children container
        var wrapper = document.createElement('div');
        wrapper.className = 'fb-entry-wrapper';

        var row = document.createElement('div');
        row.className = 'fb-entry' + (isDir ? ' is-dir' : '');
        row.dataset.url  = url;
        row.dataset.type = entry.type || 'file';
        if (clipboard && clipboard.mode === 'cut' && clipboard.items.some(function(it) { return it.url === url; })) {
            row.classList.add('fb-cut');
        }
        if (selectedSet.has(url)) {
            row.classList.add('active');
        }

        // Name cell: indent + toggle + icon + name
        var nameCell = document.createElement('span');
        nameCell.className = 'fb-entry-name-cell';

        var indent = document.createElement('span');
        indent.className = 'fb-entry-indent';
        indent.style.width = (depth * 12) + 'px';
        nameCell.appendChild(indent);

        var toggle = document.createElement('span');
        toggle.className = 'fb-entry-toggle';
        toggle.textContent = isDir ? '\u25B6' : '';  // ▶ for dirs, blank for files
        nameCell.appendChild(toggle);

        var icon = document.createElement('span');
        icon.className = 'fb-entry-icon';
        icon.textContent = fileIcon(entry, isDir && libraryUrls.has(url));
        nameCell.appendChild(icon);

        var nameEl = document.createElement('span');
        nameEl.className = 'fb-entry-name';
        nameEl.textContent = entry.basename || basename(url);
        nameEl.title = url;
        nameCell.appendChild(nameEl);

        // Size cell
        var sizeEl = document.createElement('span');
        sizeEl.className = 'fb-entry-size';
        if (entry.size != null) sizeEl.textContent = fmtSize(entry.size);

        // Modified cell
        var mtimeEl = document.createElement('span');
        mtimeEl.className = 'fb-entry-mtime';
        if (entry.last_modified) mtimeEl.textContent = fmtMtime(entry.last_modified);

        row.appendChild(nameCell);
        row.appendChild(sizeEl);
        row.appendChild(mtimeEl);

        // Children container (lazy-populated)
        var childrenEl = null;
        if (isDir) {
            childrenEl = document.createElement('div');
            childrenEl.className = 'fb-children';
            treeNodes[url] = childrenEl;
        }

        // Click: select (supports ctrl/cmd-click toggle and shift-click range)
        row.addEventListener('click', function(e) {
            e.stopPropagation();
            if (e.shiftKey) {
                selectRangeTo(url, entry.type);
            } else if (e.ctrlKey || e.metaKey) {
                toggleSelect(url, entry.type);
            } else {
                selectOnly(url, entry.type);
            }
        });

        // Right-click: context menu (copy/cut/paste/rename/delete).
        // If the row is already part of a multi-selection, the menu acts on
        // the whole selection; otherwise it replaces the selection with just
        // this row.
        row.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (!selectedSet.has(url)) {
                selectOnly(url, entry.type);
            }
            showCtxMenu(e.clientX, e.clientY, { targets: ctxTargetsFromSelection(), isBackground: false });
        });

        // Toggle click: expand/collapse (stop propagation so row click doesn't fire)
        if (isDir) {
            toggle.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleDir(url, toggle, childrenEl);
            });
        }
        // Double-click on row: "Open" this entry — same as the context
        // menu's Open item. Directories reset the tree root (navigateTo);
        // files open in the editor.
        row.addEventListener('dblclick', function(e) {
            e.stopPropagation();
            openEntry({ url: url, type: entry.type, so: currentSo });
        });

        wrapper.appendChild(row);
        if (childrenEl) wrapper.appendChild(childrenEl);
        return wrapper;
    }

    function fmtMtime(ts) {
        if (!ts) return '';
        var d = new Date(parseFloat(ts) * 1000);
        var now = new Date();
        var diffDays = (now - d) / 86400000;
        if (diffDays < 1) {
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        if (diffDays < 180) {
            return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
        return d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
    }

    function toggleDir(url, toggle, childrenEl) {
        var expanded = childrenEl.classList.contains('expanded');
        if (expanded) {
            // Collapse
            childrenEl.classList.remove('expanded');
            toggle.textContent = '\u25B6';  // ▶
        } else {
            // Expand: lazy-load if not yet populated
            childrenEl.classList.add('expanded');
            toggle.textContent = '\u25BC';  // ▼
            if (!childrenEl.dataset.loaded) {
                // Show loading indicator
                var loader = document.createElement('div');
                loader.className = 'fb-child-loading';
                loader.textContent = 'Loading...';
                childrenEl.appendChild(loader);
                // Request children from host
                vscode.postMessage({ cmd: 'expandDir', url: url, storageOptions: currentSo || undefined });
            }
        }
    }

    function handleExpandResult(data) {
        var parentUrl = data.parentUrl || data.url;
        var childrenEl = treeNodes[parentUrl];
        if (!childrenEl) { dbg('no treeNode for ' + parentUrl); return; }

        childrenEl.innerHTML = '';
        childrenEl.dataset.loaded = '1';

        if (data.error) {
            var errEl = document.createElement('div');
            errEl.className = 'fb-child-loading';
            errEl.textContent = 'Error: ' + data.error;
            childrenEl.appendChild(errEl);
            return;
        }

        var rawEntries = data.entries || [];
        var entries = visibleEntries(rawEntries);
        if (rawEntries.length === 0 || entries.length === 0) {
            var emptyMsg = document.createElement('div');
            emptyMsg.className = 'fb-child-loading';
            emptyMsg.textContent = rawEntries.length === 0 ? 'Empty' : 'All items are hidden';
            childrenEl.appendChild(emptyMsg);
            return;
        }

        // Find the depth of the parent by looking at the DOM
        var parentRow = childrenEl.previousSibling;
        var parentIndent = parentRow ? (parseInt(parentRow.querySelector('.fb-entry-indent').style.width) || 0) : 0;
        var childDepth = Math.round(parentIndent / 12) + 1;

        var sorted = sortEntries(entries);
        for (var i = 0; i < sorted.length; i++) {
            childrenEl.appendChild(makeEntryRow(sorted[i], childDepth));
        }
        dbg('expanded ' + parentUrl + ': ' + sorted.length + ' children');
    }

    function renderBrowse(data) {
        dbg('renderBrowse url=' + data.url + ' entries=' + (data.entries ? data.entries.length : 'none') + ' error=' + data.error);
        currentUrl = data.url || '';
        urlInput.value = currentUrl;
        renderBreadcrumb(currentUrl);

        // Reset tree node map and stored entries
        treeNodes = {};
        lastBrowseEntries = [];
        // Selection is scoped to the current listing — a fresh listing
        // (navigation, refresh, or post-paste/delete reload) always clears
        // it. The copy/cut clipboard is a separate concern and survives this.
        selectedSet = new Map();
        anchorUrl = null;

        entriesEl.innerHTML = '';
        emptyEl.classList.add('hidden');
        errorEl.classList.add('hidden');

        if (data.error) {
            errorEl.textContent = 'Error: ' + data.error;
            errorEl.classList.remove('hidden');
            updateSelectionUI();
            return;
        }

        lastBrowseEntries = data.entries || [];
        renderRootEntries();
        dbg('rendered ' + lastBrowseEntries.length + ' raw entries (showHidden=' + showHidden + ')');
        updateSelectionUI();
    }

    // ── multi-select ───────────────────────────────────────────────────────
    function allRows() {
        return Array.from((_fbRoot === document ? document : _fbRoot).querySelectorAll('.fb-entry'));
    }
    function ctxTargetsFromSelection() {
        return Array.from(selectedSet.entries()).map(function(e) {
            return { url: e[0], type: e[1].type, so: e[1].so };
        });
    }
    function selectOnly(url, type) {
        selectedSet = new Map([[url, { type: type, so: currentSo }]]);
        anchorUrl = url;
        updateSelectionUI();
    }
    function toggleSelect(url, type) {
        if (selectedSet.has(url)) {
            selectedSet.delete(url);
        } else {
            selectedSet.set(url, { type: type, so: currentSo });
        }
        anchorUrl = url;
        updateSelectionUI();
    }
    function selectRangeTo(url, type) {
        var rows = allRows();
        var urls = rows.map(function(r) { return r.dataset.url; });
        var i1 = anchorUrl ? urls.indexOf(anchorUrl) : -1;
        var i2 = urls.indexOf(url);
        if (i1 < 0) i1 = i2;
        var lo = Math.min(i1, i2), hi = Math.max(i1, i2);
        var next = new Map();
        for (var i = lo; i <= hi && i >= 0 && i < rows.length; i++) {
            next.set(rows[i].dataset.url, { type: rows[i].dataset.type, so: currentSo });
        }
        selectedSet = next;
        updateSelectionUI();
    }
    function clearSelection() {
        selectedSet = new Map();
        anchorUrl = null;
        updateSelectionUI();
    }

    // Re-renders the .active class on all rows and the info panel to match
    // `selectedSet`. Single selection reuses the existing inspect/scan info
    // view; multi-selection shows a lightweight "N items selected" summary.
    // Copy/cut/paste/rename/delete are all done via the right-click context
    // menu, so the info-pane actions row is only ever used for "+ Library",
    // which only applies to a single selected directory.
    function updateSelectionUI() {
        allRows().forEach(function(row) {
            row.classList.toggle('active', selectedSet.has(row.dataset.url));
        });

        if (selectedSet.size === 0) {
            selected = null;
            infoTitle.textContent = 'No file selected';
            infoActions.classList.add('hidden');
            infoMeta.innerHTML = '';
            infoPreview.innerHTML = '';
            if (scanPane) scanPane.classList.add('hidden');
            return;
        }

        if (selectedSet.size === 1) {
            var entry = selectedSet.entries().next().value;
            selected = { url: entry[0], type: entry[1].type, so: entry[1].so };
            showSingleSelectionInfo(selected.url, selected.type);
            return;
        }

        // Multi-select summary — no info-pane actions apply.
        selected = null;
        infoActions.classList.add('hidden');
        infoTitle.textContent = selectedSet.size + ' items selected';
        infoMeta.innerHTML = '';
        infoPreview.innerHTML = '';
        if (scanPane) scanPane.classList.add('hidden');
        if (scanPanelRoot) scanPanelRoot.classList.remove('hidden');
        if (fileContent) { fileContent.classList.add('hidden'); fileContent.innerHTML = ''; }
        if (typeof window.__fbPanelDeliver === 'function') {
            window.__fbPanelDeliver({ type: 'data', library: {}, info: {}, enums: {} });
        }
    }

    function showSingleSelectionInfo(url, type) {
        dbg('selected ' + type + ': ' + url);

        infoTitle.textContent = basename(url);

        const isFile = type !== 'directory';
        selectedIsFile = isFile;
        // "+ Library" is the only remaining info-pane action (Open, Rename,
        // and Delete are all available via the right-click context menu
        // instead). It only applies to a directory that (a) isn't already
        // in the library and (b) actually matched a recognised project
        // type when scanned — hide the row for now; for a directory,
        // updateAddToLibButtonVisibility() decides once the scan result
        // (projectScanned) arrives, avoiding a flash of a button that's
        // about to disappear.
        infoActions.classList.add('hidden');

        infoMeta.innerHTML = '';
        infoPreview.innerHTML = '';

        // Reset both scan pane variants on every selection change.
        // Also send an empty library to the embedded panel so the previous
        // directory's project widget and details are cleared immediately.
        if (scanPane) {
            scanPane.classList.add('hidden');
            if (scanStatus) scanStatus.textContent = '';
        }
        if (scanPanelRoot) scanPanelRoot.classList.remove('hidden');
        if (fileContent)   { fileContent.classList.add('hidden'); fileContent.innerHTML = ''; }
        if (typeof window.__fbPanelDeliver === 'function') {
            window.__fbPanelDeliver({ type: 'data', library: {}, info: {}, enums: {} });
        }

        if (isFile) {
            // Show scan pane immediately with loading indicator — it gets populated
            // when both inspectResult and projectScanned arrive
            if (scanPane) {
                scanPane.classList.remove('hidden');
                if (scanStatus) scanStatus.textContent = 'inspecting...';
            }
            dbg('posting inspect for ' + url);
            vscode.postMessage({ cmd: 'inspect', url: url, storageOptions: currentSo || undefined });
        } else {
            renderMeta({ type: 'directory', url: url });
            // Trigger projspec scan on directory selection
            if (scanPane) {
                scanPane.classList.remove('hidden');
                if (scanStatus) scanStatus.textContent = 'scanning...';
            }
            dbg('posting scanDir for ' + url);
            vscode.postMessage({ cmd: 'scanDir', url: url, storageOptions: currentSo || undefined });
        }
    }

    function renderBreadcrumb(url) {
        breadcrumb.innerHTML = '';
        if (!url) return;
        const protoMatch = url.match(/^([a-z][a-z0-9+.\-]*):\/\//i);
        let proto = '';
        let rest = url;
        if (protoMatch) {
            proto = protoMatch[0];
            rest = url.slice(proto.length);
        }
        // Absolute local-style paths (file:///Users/...) leave a leading
        // '/' in `rest` after the two protocol slashes are stripped off —
        // that's the root slash, not a path segment separator. Remember
        // it so the reconstructed segment targets below keep it (otherwise
        // clicking "Users" would rebuild the URL as the malformed
        // file://Users, which the backend treats as a *relative* path
        // instead of an absolute one). Remote-style URLs with no root
        // slash convention (s3://bucket/key) are unaffected.
        const hasRootSlash = rest.charAt(0) === '/';
        const parts = rest.replace(/\/+$/, '').split('/').filter(Boolean);
        if (proto) {
            const rootTarget = proto + (hasRootSlash ? '/' : '');
            const link = document.createElement('span');
            link.className = 'bc-seg';
            link.textContent = proto;
            link.title = rootTarget;
            link.addEventListener('click', function() { navigateTo(rootTarget, currentSo); });
            breadcrumb.appendChild(link);
        }
        let accumulated = proto + (hasRootSlash ? '/' : '');
        for (let i = 0; i < parts.length; i++) {
            accumulated += (accumulated.slice(-1) === '/' ? '' : '/') + parts[i];
            const sep = document.createElement('span');
            sep.className = 'bc-sep';
            sep.textContent = ' / ';
            breadcrumb.appendChild(sep);
            const link = document.createElement('span');
            link.className = 'bc-seg';
            link.textContent = parts[i];
            const target = accumulated;
            link.title = target;
            link.addEventListener('click', function() { navigateTo(target, currentSo); });
            breadcrumb.appendChild(link);
        }
    }

     function renderMeta(data) {
        infoMeta.innerHTML = '';
        var rows = [];
        // Don't show data.type — it's the JS message type, not a file type
        if (data.size != null)  rows.push(['Size', fmtSize(data.size)]);
        if (data.last_modified) rows.push(['Modified', fmtDate(data.last_modified)]);
        if (data.mime_type)     rows.push(['MIME', data.mime_type]);
        for (var i = 0; i < rows.length; i++) {
            const row = document.createElement('div');
            row.className = 'info-row';
            row.innerHTML = '<span class="info-key">' + escHtml(rows[i][0]) + '</span><span>' + escHtml(String(rows[i][1])) + '</span>';
            infoMeta.appendChild(row);
        }
    }

    function renderInspect(data) {
        dbg('renderInspect name=' + data.name + ' error=' + data.error);
        // For files: only show MIME in the meta strip — size/modified are already
        // visible in the file tree columns and would be redundant here.
        // The intake type and text preview now live in the scan pane below.
        infoMeta.innerHTML = '';
        if (data.mime_type) {
            const row = document.createElement('div');
            row.className = 'info-row';
            row.innerHTML = '<span class="info-key">MIME</span><span>' + escHtml(data.mime_type) + '</span>';
            infoMeta.appendChild(row);
        }
        // Clear preview — content is in the scan pane
        infoPreview.innerHTML = '';
    }

    // ── context menu (copy/cut/paste/rename/delete) ───────────────────────
    function showCtxMenu(x, y, target) {
        // target = { targets: [{url, type, so}, ...], isBackground }
        ctxTarget = target;
        var n = target.targets.length;
        var items = ctxMenu.querySelectorAll('.fb-ctxmenu-item');
        items.forEach(function(item) {
            var action = item.dataset.action;
            var show = true;
            var disabled = false;
            if (target.isBackground) {
                show = action === 'paste';
                if (action === 'paste') disabled = !clipboard;
            } else {
                if (action === 'open') {
                    // Open only makes sense for exactly one item.
                    show = n === 1;
                } else if (action === 'rename') {
                    // Rename only makes sense for exactly one item.
                    show = n === 1;
                } else if (action === 'paste') {
                    // Paste-into-folder only offered when right-clicking a
                    // single directory (pasting into several dirs at once
                    // is ambiguous). Background right-click (above) is the
                    // way to paste into the currently browsed directory.
                    show = n === 1 && target.targets[0].type === 'directory';
                    disabled = !clipboard;
                }
            }
            item.classList.toggle('hidden', !show);
            item.classList.toggle('disabled', disabled);
        });
        ctxMenu.classList.remove('hidden');
        ctxMenu.style.left = x + 'px';
        ctxMenu.style.top = y + 'px';
        requestAnimationFrame(function() {
            var rect = ctxMenu.getBoundingClientRect();
            var vw = window.innerWidth, vh = window.innerHeight;
            if (rect.right > vw)  ctxMenu.style.left = Math.max(0, vw - rect.width - 4) + 'px';
            if (rect.bottom > vh) ctxMenu.style.top  = Math.max(0, vh - rect.height - 4) + 'px';
        });
    }
    function hideCtxMenu() {
        ctxMenu.classList.add('hidden');
        ctxTarget = null;
    }
    // Right-click on empty space in the file list: paste-into-current-dir only.
    $fbId('fb-file-list').addEventListener('contextmenu', function(e) {
        if (e.target.closest && e.target.closest('.fb-entry')) return;  // handled by row listener
        e.preventDefault();
        showCtxMenu(e.clientX, e.clientY, {
            targets: [{ url: currentUrl, so: currentSo, type: 'directory' }],
            isBackground: true,
        });
    });
    // Plain left-click on empty space clears the current multi-selection
    // (modifier-clicks are reserved for range/toggle-select on rows, so a
    // background click never carries one that matters here).
    $fbId('fb-file-list').addEventListener('click', function(e) {
        if (e.target.closest && e.target.closest('.fb-entry')) return;
        clearSelection();
    });

    function clearCutVisual() {
        (_fbRoot === document ? document : _fbRoot).querySelectorAll('.fb-entry.fb-cut').forEach(function(el) { el.classList.remove('fb-cut'); });
    }
    function markCutVisual(url) {
        var sel = '.fb-entry[data-url="' + (window.CSS && CSS.escape ? CSS.escape(url) : url) + '"]';
        var row = (_fbRoot === document ? document : _fbRoot).querySelector(sel);
        if (row) row.classList.add('fb-cut');
    }
    // targets: [{url, type, so}, ...]
    function setClipboard(targets, mode) {
        clearCutVisual();
        clipboard = {
            items: targets.map(function(t) { return { url: t.url, so: t.so, type: t.type }; }),
            mode: mode,
        };
        if (mode === 'cut') {
            clipboard.items.forEach(function(it) { markCutVisual(it.url); });
        }
        dbg('clipboard: ' + mode + ' ' + clipboard.items.length + ' item(s)');
    }
    // targets: [{url, type, so}, ...]
    function deleteEntriesFor(targets) {
        if (!targets.length) return;
        dbg('deleteEntries ' + targets.length + ' item(s)');
        vscode.postMessage({
            cmd: 'deleteEntries',
            items: targets.map(function(t) {
                return { url: t.url, isDir: t.type === 'directory', storageOptions: t.so || undefined };
            }),
        });
    }
    function openRenameModalFor(url, so) {
        renameTarget = { url: url, so: so };
        renInput.value = basename(url);
        renOverlay.classList.remove('hidden');
        setTimeout(function() { renInput.focus(); }, 0);
    }
    // "Open" context-menu action: for a file this is identical to the
    // info-pane's Open button (opens it in the editor); for a directory
    // it resets the browser tree root to that directory, same as a
    // double-click on the row.
    function openEntry(target) {
        if (target.type === 'directory') {
            navigateTo(target.url, target.so);
        } else {
            dbg('openFile ' + target.url);
            vscode.postMessage({ cmd: 'openFile', url: target.url, storageOptions: target.so || undefined });
        }
    }
    // items: [{url, so}, ...]
    function sendPaste(items, dstDir, dstSo, mode, confirmed) {
        dbg('paste ' + mode + ' ' + items.length + ' item(s) -> ' + dstDir);
        vscode.postMessage({
            cmd: 'paste',
            items: items.map(function(it) { return { src: it.url, srcStorageOptions: it.so || undefined }; }),
            dstDir: dstDir,
            dstStorageOptions: dstSo || undefined,
            mode: mode,
            confirmed: !!confirmed,
        });
    }
    function doPaste(target) {
        if (!clipboard || !clipboard.items.length) return;
        var dstDir = target.isBackground ? currentUrl : target.targets[0].url;
        var dstSo  = target.isBackground ? currentSo  : target.targets[0].so;
        sendPaste(clipboard.items, dstDir, dstSo, clipboard.mode, false);
    }

    // Context-menu action dispatch.
    ctxMenu.addEventListener('click', function(e) {
        var item = e.target.closest('.fb-ctxmenu-item');
        if (!item || item.classList.contains('disabled') || item.classList.contains('hidden')) return;
        var action = item.dataset.action;
        var target = ctxTarget;
        hideCtxMenu();
        if (!target) return;
        if (action === 'open') {
            if (target.targets.length === 1) openEntry(target.targets[0]);
        } else if (action === 'copy') {
            setClipboard(target.targets, 'copy');
        } else if (action === 'cut') {
            setClipboard(target.targets, 'cut');
        } else if (action === 'paste') {
            doPaste(target);
        } else if (action === 'rename') {
            if (target.targets.length === 1) openRenameModalFor(target.targets[0].url, target.targets[0].so);
        } else if (action === 'delete') {
            deleteEntriesFor(target.targets);
        }
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (!ctxMenu.classList.contains('hidden')) { hideCtxMenu(); return; }
            if (selectedSet.size > 0) { clearSelection(); }
        }
    });

    // Paste size-confirmation modal
    $fbId('paste-confirm-cancel').addEventListener('click', function() {
        pendingPaste = null;
        pasteConfirmOverlay.classList.add('hidden');
    });
    $fbId('paste-confirm-ok').addEventListener('click', function() {
        pasteConfirmOverlay.classList.add('hidden');
        if (!pendingPaste) return;
        sendPaste(pendingPaste.items, pendingPaste.dstDir, pendingPaste.dstSo, pendingPaste.mode, true);
        pendingPaste = null;
    });
    pasteConfirmOverlay.addEventListener('click', function(e) {
        if (e.target === pasteConfirmOverlay) {
            pendingPaste = null;
            pasteConfirmOverlay.classList.add('hidden');
        }
    });

    // ── navigation ─────────────────────────────────────────────────────────
    function navigateTo(url, so, push) {
        const shouldPush = push !== false;
        dbg('navigateTo push=' + shouldPush + ' url=' + url);
        vscode.postMessage({ cmd: 'browse', url: url, storageOptions: so || undefined, push: shouldPush });
        selected = null;
        hideCtxMenu();
        infoTitle.textContent = 'Loading...';
        infoActions.classList.add('hidden');
        infoMeta.innerHTML = '';
        infoPreview.innerHTML = '';
    }

    // ── bookmarks ──────────────────────────────────────────────────────────
    function refreshLibraryBadges() {
        // Walk every directory row in the DOM and swap the folder icon
        document.querySelectorAll('.fb-entry[data-type="directory"]').forEach(function(row) {
            var url = row.dataset.url || '';
            var iconEl = row.querySelector('.fb-entry-icon');
            if (!iconEl) return;
            iconEl.textContent = libraryUrls.has(url) ? '\uD83D\uDDC2\uFE0F' : '\uD83D\uDCC1'; // 🗂️ or 📁
        });
    }

    function renderBookmarks() {
        bmList.innerHTML = '';
        if (!bookmarks.length) {
            const e = document.createElement('div');
            e.className = 'bm-empty';
            e.textContent = 'No bookmarks yet.';
            bmList.appendChild(e);
            return;
        }
        for (var i = 0; i < bookmarks.length; i++) {
            const bm = bookmarks[i];
            const row = document.createElement('div');
            row.className = 'bm-item';
            const info = document.createElement('div');
            info.style.flex = '1';
            info.style.overflow = 'hidden';
            const lbl = document.createElement('div');
            lbl.className = 'bm-item-label';
            lbl.textContent = bm.label || bm.url;
            const urlDiv = document.createElement('div');
            urlDiv.className = 'bm-item-url';
            urlDiv.textContent = bm.url;
            info.appendChild(lbl);
            info.appendChild(urlDiv);
            // Show a key icon if the bookmark has stored storage_options
            if (bm.storage_options && Object.keys(bm.storage_options).length > 0) {
                const soTag = document.createElement('div');
                soTag.className = 'bm-item-so';
                soTag.title = 'Saved storage options: ' + JSON.stringify(bm.storage_options);
                soTag.textContent = '\uD83D\uDD11 credentials stored';
                info.appendChild(soTag);
            }
            const rm = document.createElement('button');
            rm.className = 'bm-remove';
            rm.title = 'Remove bookmark';
            rm.textContent = 'X';
            const bmUrl = bm.url;
            // Serialise the bookmark's own storage_options as a JSON string (or '').
            // These are scoped to this URL only — they replace currentSo entirely
            // when navigating to a different protocol/host.
            const bmSo = (bm.storage_options && Object.keys(bm.storage_options).length > 0)
                ? JSON.stringify(bm.storage_options) : '';
            rm.addEventListener('click', function(e) {
                e.stopPropagation();
                vscode.postMessage({ cmd: 'removeBookmark', url: bmUrl });
            });
            row.appendChild(info);
            row.appendChild(rm);
            row.addEventListener('click', function(ev) {
                if (ev.target === rm) return;
                bmPanel.classList.add('hidden');
                // Switch currentSo to the bookmark's own options (may be empty)
                currentSo = bmSo;
                navigateTo(bmUrl, bmSo);
            });
            bmList.appendChild(row);
        }
    }

    // ── toolbar ────────────────────────────────────────────────────────────
    $fbId('btn-back').addEventListener('click', function() {
        if (histIdx > 0) {
            histIdx--;
            const h = history[histIdx];
            currentSo = h.so;
            dbg('back to ' + h.url);
            vscode.postMessage({ cmd: 'browse', url: h.url, storageOptions: h.so || undefined, push: false });
            selected = null;
            infoTitle.textContent = 'Loading...';
            infoActions.classList.add('hidden');
            infoMeta.innerHTML = '';
            infoPreview.innerHTML = '';
        }
    });
    $fbId('btn-up').addEventListener('click', function() {
        const p = parentUrl(currentUrl);
        if (p && p !== currentUrl) { navigateTo(p, currentSo); }
    });
    $fbId('btn-refresh').addEventListener('click', function() {
        navigateTo(currentUrl, currentSo, false);
    });
    $fbId('btn-bm-dropdown').addEventListener('click', function(e) {
        e.stopPropagation();
        bmPanel.classList.toggle('hidden');
        if (!bmPanel.classList.contains('hidden')) renderBookmarks();
    });
    $fbId('bm-close').addEventListener('click', function() {
        bmPanel.classList.add('hidden');
    });
    $fbId('btn-bm-add-current').addEventListener('click', function() {
        bmPanel.classList.add('hidden');
        vscode.postMessage({ cmd: 'addBookmark', url: currentUrl, storageOptions: currentSo || undefined });
    });
    document.addEventListener('click', function(e) {
        if (!bmPanel.contains(e.target) && e.target !== $fbId('btn-bm-dropdown')) {
            bmPanel.classList.add('hidden');
        }
        if (!ctxMenu.contains(e.target) && !ctxMenu.classList.contains('hidden')) {
            hideCtxMenu();
        }
    });

    // Storage options
    $fbId('btn-so').addEventListener('click', function(e) {
        e.stopPropagation();
        soInput.value = currentSo;
        soOverlay.classList.remove('hidden');
        setTimeout(function() { soInput.focus(); }, 0);
    });
    $fbId('so-cancel').addEventListener('click', function() {
        soOverlay.classList.add('hidden');
    });
    $fbId('so-ok').addEventListener('click', function() {
        const val = soInput.value.trim();
        try {
            if (val) JSON.parse(val);
            currentSo = val;
        } catch(ex) {
            alert('Storage options must be valid JSON: ' + ex.message);
            return;
        }
        soOverlay.classList.add('hidden');
        dbg('storage options set: ' + currentSo);
    });
    soOverlay.addEventListener('click', function(e) {
        if (e.target === soOverlay) soOverlay.classList.add('hidden');
    });

    // Show hidden files/directories — off by default. Re-renders the
    // current listing from cache (no network round-trip); any expanded
    // subdirectories collapse and re-apply the filter when re-expanded.
    $fbId('fb-show-hidden').addEventListener('change', function(e) {
        showHidden = !!e.target.checked;
        dbg('showHidden = ' + showHidden);
        renderRootEntries();
    });

    // Go / URL bar
    $fbId('btn-go').addEventListener('click', function() {
        const url = urlInput.value.trim();
        if (url) { navigateTo(url, currentSo); }
    });
    urlInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            const url = urlInput.value.trim();
            if (url) { navigateTo(url, currentSo); }
        }
    });

    // New file / folder
    $fbId('btn-new-file').addEventListener('click', function() {
        newentryMode = 'file';
        neTitle.textContent = 'New file';
        neInput.value = '';
        neOverlay.classList.remove('hidden');
        setTimeout(function() { neInput.focus(); }, 0);
    });
    $fbId('btn-new-dir').addEventListener('click', function() {
        newentryMode = 'dir';
        neTitle.textContent = 'New folder';
        neInput.value = '';
        neOverlay.classList.remove('hidden');
        setTimeout(function() { neInput.focus(); }, 0);
    });
    $fbId('newentry-cancel').addEventListener('click', function() {
        neOverlay.classList.add('hidden');
    });
    $fbId('newentry-ok').addEventListener('click', function() {
        const name = neInput.value.trim();
        if (!name) return;
        neOverlay.classList.add('hidden');
        if (newentryMode === 'file') {
            dbg('createFile ' + name);
            vscode.postMessage({ cmd: 'createFile', parentUrl: currentUrl, name: name, storageOptions: currentSo || undefined });
        } else {
            dbg('mkdir ' + name);
            vscode.postMessage({ cmd: 'mkdir', parentUrl: currentUrl, name: name, storageOptions: currentSo || undefined });
        }
    });
    neInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') $fbId('newentry-ok').click();
        if (e.key === 'Escape') neOverlay.classList.add('hidden');
    });
    neOverlay.addEventListener('click', function(e) {
        if (e.target === neOverlay) neOverlay.classList.add('hidden');
    });

    // Info panel actions
    $fbId('btn-add-to-lib').addEventListener('click', function() {
        if (!selected) return;
        dbg('addToLibrary ' + selected.url);
        vscode.postMessage({ cmd: 'addToLibrary', url: selected.url, storageOptions: selected.so || undefined });
    });

    // Rename modal
    $fbId('rename-cancel').addEventListener('click', function() {
        renameTarget = null;
        renOverlay.classList.add('hidden');
    });
    $fbId('rename-ok').addEventListener('click', function() {
        const newName = renInput.value.trim();
        if (!newName || !renameTarget) return;
        renOverlay.classList.add('hidden');
        dbg('rename ' + renameTarget.url + ' -> ' + newName);
        vscode.postMessage({ cmd: 'renameEntry', url: renameTarget.url, newName: newName, storageOptions: renameTarget.so || undefined });
        renameTarget = null;
    });
    renInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') $fbId('rename-ok').click();
        if (e.key === 'Escape') { renameTarget = null; renOverlay.classList.add('hidden'); }
    });
    renOverlay.addEventListener('click', function(e) {
        if (e.target === renOverlay) { renameTarget = null; renOverlay.classList.add('hidden'); }
    });

    // ── embedded projspec panel ────────────────────────────────────────────
    // The shared panel JS was already run by the inline bootstrap script in
    // getHtml() before this IIFE executed.  The bootstrap installed
    // window.__fbPanelDeliver(msg) — call it to push a data message into
    // the embedded panel.

    // ── file content display (inline, no project widget) ─────────────────
    // For single-file selections we render content directly rather than
    // routing through the embedded library panel.  The rule:
    //   - If the file has meaningful data info (datatype + schema/metadata),
    //     show that.  Text preview is suppressed — the data description is
    //     the useful thing.
    //   - Otherwise show the text preview (first N lines).
    //   - If neither is available, hide the scan pane.
    function showFileInScanPane(data) {
        if (!scanPane || !fileContent) return;

        // Switch: hide the embedded panel root, show the file content div
        if (scanPanelRoot) scanPanelRoot.classList.add('hidden');
        fileContent.classList.remove('hidden');
        fileContent.innerHTML = '';

        var proj = data.project;
        var textPreview = data.text_preview || '';

        // Extract the dataset content from the data_project spec
        var dataset = null;
        if (proj && proj.specs && proj.specs.data_project) {
            var cont = proj.specs.data_project._contents || {};
            var keys = Object.keys(cont);
            for (var i = 0; i < keys.length; i++) {
                var item = cont[keys[i]];
                if (item && item.klass && item.klass[1] === 'dataset') {
                    dataset = item;
                    break;
                }
            }
        }

        var hasData = dataset && (
            dataset.datatype ||
            (dataset.schema && Object.keys(dataset.schema).length > 0) ||
            (dataset.metadata && Object.keys(dataset.metadata).length > 0)
        );

        if (hasData) {
            var card = document.createElement('div');
            card.className = 'fc-dataset';

            // Datatype heading
            if (dataset.datatype) {
                var dtEl = document.createElement('div');
                dtEl.className = 'fc-datatype';
                dtEl.textContent = dataset.datatype;
                card.appendChild(dtEl);
            }

            var meta = dataset.metadata || {};

            // HTML repr — render inline (sanitised: strip scripts/iframes)
            var htmlRepr = typeof meta.html_repr === 'string' ? meta.html_repr : null;
            if (htmlRepr) {
                var reprDiv = document.createElement('div');
                reprDiv.className = 'fc-html-repr';
                reprDiv.innerHTML = sanitizeHtmlRepr(htmlRepr);
                card.appendChild(reprDiv);
            }

            // Thumbnail image (data: URI only)
            var thumb = typeof meta.thumbnail === 'string' ? meta.thumbnail : null;
            if (thumb && /^data:image\//i.test(thumb)) {
                var img = document.createElement('img');
                img.src = thumb;
                img.className = 'fc-thumbnail';
                img.alt = 'thumbnail';
                card.appendChild(img);
            }

            // Schema / columns — only if no richer HTML repr
            if (!htmlRepr) {
                var schema = dataset.schema;
                if (schema && typeof schema === 'object' && !Array.isArray(schema)) {
                    var cols = Object.keys(schema);
                    if (cols.length > 0) {
                        var schemaHdr = document.createElement('div');
                        schemaHdr.className = 'fc-schema-hdr';
                        schemaHdr.textContent = 'Columns';
                        card.appendChild(schemaHdr);
                        for (var ci = 0; ci < cols.length; ci++) {
                            var colRow = document.createElement('div');
                            colRow.className = 'fc-col-row';
                            colRow.innerHTML = '<span class="fc-col-name">' + escHtml(cols[ci]) + '</span>'
                                + '<span class="fc-col-dtype">' + escHtml(String(schema[cols[ci]])) + '</span>';
                            card.appendChild(colRow);
                        }
                    }
                }
            }

            // Metadata key-values — skip html_repr/thumbnail (already rendered above).
            // reader_* / readers* fields are collected into a collapsible box at the end.
            var SKIP_META = new Set(['html_repr', 'thumbnail']);
            var mkeys = Object.keys(meta);
            var readerRows = [];
            for (var mi = 0; mi < mkeys.length; mi++) {
                var mk = mkeys[mi], mv = meta[mk];
                if (SKIP_META.has(mk) || mv == null) continue;
                var mvStr = typeof mv === 'object' ? JSON.stringify(mv) : String(mv);
                if (!mvStr || mvStr === '{}' || mvStr === '[]') continue;
                if (/^readers?(_|$)/i.test(mk) || mk === 'errors') {
                    readerRows.push([mk, mvStr]);
                    continue;
                }
                var kvEl = document.createElement('div');
                kvEl.className = 'fc-kv';
                kvEl.innerHTML = '<span class="fc-k">' + escHtml(mk) + ':</span>'
                    + '<span class="fc-v">' + escHtml(mvStr) + '</span>';
                card.appendChild(kvEl);
            }
            if (readerRows.length > 0) {
                var det = document.createElement('details');
                det.className = 'fc-reader-details';
                var sum = document.createElement('summary');
                sum.className = 'fc-reader-summary';
                sum.textContent = 'Reader info';
                det.appendChild(sum);
                for (var ri = 0; ri < readerRows.length; ri++) {
                    var rkvEl = document.createElement('div');
                    rkvEl.className = 'fc-kv';
                    rkvEl.innerHTML = '<span class="fc-k">' + escHtml(readerRows[ri][0]) + ':</span>'
                        + '<span class="fc-v">' + escHtml(readerRows[ri][1]) + '</span>';
                    det.appendChild(rkvEl);
                }
                card.appendChild(det);
            }

            // Structure tags (e.g. ["table"])
            var structure = dataset.structure;
            if (Array.isArray(structure) && structure.length > 0) {
                var stEl = document.createElement('div');
                stEl.className = 'fc-kv';
                stEl.innerHTML = '<span class="fc-k">structure:</span>'
                    + '<span class="fc-v">' + escHtml(structure.join(', ')) + '</span>';
                card.appendChild(stEl);
            }

            fileContent.appendChild(card);

            // For data files, also show text preview below if there's no html_repr
            // (e.g. CSV — the first few rows are more useful than just column names)
            if (!htmlRepr && textPreview) {
                var prevHdr = document.createElement('div');
                prevHdr.className = 'fc-schema-hdr';
                prevHdr.style.marginTop = '10px';
                prevHdr.textContent = 'Preview';
                fileContent.appendChild(prevHdr);
                var pre2 = document.createElement('pre');
                pre2.className = 'fc-text-preview';
                pre2.textContent = textPreview;
                fileContent.appendChild(pre2);
            }

        } else if (textPreview) {
            // Pure text file — just show the preview
            var pre = document.createElement('pre');
            pre.className = 'fc-text-preview';
            pre.textContent = textPreview;
            fileContent.appendChild(pre);

        } else {
            // Nothing to show — hide the scan pane
            scanPane.classList.add('hidden');
        }
    }

    // Minimal sanitiser for html_repr content (strips scripts, iframes, on* handlers)
    function sanitizeHtmlRepr(html) {
        var tpl = document.createElement('template');
        tpl.innerHTML = String(html);
        var walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT);
        var toRemove = [];
        var n = walker.nextNode();
        while (n) {
            var tag = n.tagName.toLowerCase();
            if (tag === 'script' || tag === 'iframe' || tag === 'object' || tag === 'embed') {
                toRemove.push(n);
            } else {
                var attrs = Array.from(n.attributes);
                for (var ai = 0; ai < attrs.length; ai++) {
                    var an = attrs[ai].name.toLowerCase();
                    if (an.startsWith('on')) { n.removeAttribute(attrs[ai].name); continue; }
                    if ((an === 'href' || an === 'src') && /^\s*javascript:/i.test(attrs[ai].value)) {
                        n.removeAttribute(attrs[ai].name);
                    }
                }
            }
            n = walker.nextNode();
        }
        for (var ri = 0; ri < toRemove.length; ri++) toRemove[ri].remove();
        return tpl.innerHTML;
    }

    function showProjectInPanel(data) {
        if (!scanPanelRoot) return;
        if (scanStatus) scanStatus.textContent = '';

        var proj = data.project;
        var url  = data.url || '';
        if (!proj) {
            if (scanStatus) scanStatus.textContent = data.error || 'no project data';
            return;
        }

        var lib = {};
        lib[url] = proj;
        // Pass info and enums so spec documentation popups and enum labels work
        var dataMsg = { type: 'data', library: lib, info: data.info || {}, enums: data.enums || {} };

        if (typeof window.__fbPanelDeliver === 'function') {
            dbg('delivering to embedded panel: ' + url);
            window.__fbPanelDeliver(dataMsg);
        } else {
            dbg('ERROR: __fbPanelDeliver not available');
        }
    }

    // Show "+ Library" only for a directory that (a) isn't already in the
    // library and (b) matched at least one recognised project type when
    // scanned (i.e. `project.specs` is non-empty). Guards against a stale
    // scan result arriving after the user has since selected something
    // else.
    function updateAddToLibButtonVisibility(url, project) {
        if (!selected || selected.url !== url || selectedIsFile) return;
        var hasSpecs = !!(project && project.specs && Object.keys(project.specs).length > 0);
        var show = hasSpecs && !libraryUrls.has(url);
        infoActions.classList.toggle('hidden', !show);
        if (show) { $fbId('btn-add-to-lib').style.display = ''; }
    }

    // ── message bus ────────────────────────────────────────────────────────
    // Inbound messages are delivered via transport.onReady(dispatch).
    function _fbDispatch(msg) {
        // (type logged selectively in each case handler)
        switch (msg.type) {
            case 'loading':
                spinner.classList.toggle('hidden', !msg.loading);
                break;

            case 'init':
                bookmarks = msg.bookmarks || [];
                protocols = msg.protocols || [];
                if (msg.libraryUrls) {
                    libraryUrls = new Set(msg.libraryUrls);
                    dbg('init: ' + bookmarks.length + ' bookmarks, ' + libraryUrls.size + ' library entries');
                } else {
                    dbg('init: ' + bookmarks.length + ' bookmarks, ' + protocols.length + ' protocols');
                }
                break;

            case 'browseResult':
                if (typeof msg.storageOptions === 'string') {
                    currentSo = msg.storageOptions;
                }
                renderBrowse(msg);
                if (msg.pushHistory) {
                    history = history.slice(0, histIdx + 1);
                    history.push({ url: msg.url, so: currentSo });
                    histIdx = history.length - 1;
                    dbg('history push, depth=' + history.length);
                }
                break;

            case 'inspectResult':
                renderInspect(msg);
                break;

            case 'expandResult':
                handleExpandResult(msg);
                break;

            case 'projectScanned':
                dbg('projectScanned url=' + msg.url);
                if (selectedIsFile) {
                    // Single file: inline display, no project widget
                    showFileInScanPane(msg);
                } else {
                    // Directory: full embedded library panel
                    showProjectInPanel(msg);
                    updateAddToLibButtonVisibility(msg.url, msg.project);
                }
                break;

            case 'bookmarksUpdated':
                bookmarks = msg.bookmarks || [];
                dbg('bookmarks updated: ' + bookmarks.length);
                if (!bmPanel.classList.contains('hidden')) renderBookmarks();
                break;

            case 'libraryUrlsUpdated':
                libraryUrls = new Set(msg.libraryUrls || []);
                dbg('library URLs updated: ' + libraryUrls.size);
                refreshLibraryBadges();
                // If the currently selected directory just became a
                // library member (e.g. the user clicked +Library), hide
                // the now-irrelevant action row immediately rather than
                // waiting for a re-selection/re-scan.
                if (selected && !selectedIsFile && libraryUrls.has(selected.url)) {
                    infoActions.classList.add('hidden');
                }
                break;

            case 'pasteResult':
                if (msg.error) {
                    errorEl.textContent = 'Paste error: ' + msg.error;
                    errorEl.classList.remove('hidden');
                    dbg('paste error: ' + msg.error);
                } else {
                    var pResults = msg.results || [];
                    var pFailed = pResults.filter(function(r) { return r.error; });
                    if (pFailed.length) {
                        errorEl.textContent = 'Paste: ' + (pResults.length - pFailed.length) + ' of ' +
                            pResults.length + ' item(s) succeeded. Failed: ' +
                            pFailed.map(function(f) { return basename(f.src) + ' (' + f.error + ')'; }).join(', ');
                        errorEl.classList.remove('hidden');
                    }
                    if (msg.mode === 'cut') { clipboard = null; clearCutVisual(); }
                    dbg('paste ok: ' + pResults.length + ' item(s)');
                    navigateTo(currentUrl, currentSo, false);
                }
                break;

            case 'pasteNeedsConfirm':
                pendingPaste = {
                    items: msg.items, dstDir: msg.dstDir, dstSo: msg.dstStorageOptions,
                    mode: msg.mode,
                };
                pasteConfirmMsg.textContent = 'This will copy ' + fmtSize(msg.totalSize) +
                    ' (' + msg.items.length + ' item' + (msg.items.length === 1 ? '' : 's') +
                    ') into "' + msg.dstDir + '". Continue?';
                pasteConfirmOverlay.classList.remove('hidden');
                break;

            case 'deleteEntriesResult': {
                var dResults = msg.results || [];
                var dFailed = dResults.filter(function(r) { return r.error; });
                if (dFailed.length) {
                    errorEl.textContent = 'Delete: ' + (dResults.length - dFailed.length) + ' of ' +
                        dResults.length + ' item(s) succeeded. Failed: ' +
                        dFailed.map(function(f) { return basename(f.url) + ' (' + f.error + ')'; }).join(', ');
                    errorEl.classList.remove('hidden');
                }
                navigateTo(currentUrl, currentSo, false);
                break;
            }

            case 'error':
                errorEl.textContent = 'Error: ' + (msg.message || 'unknown');
                errorEl.classList.remove('hidden');
                dbg('error: ' + msg.message);
                break;
        }
    }  // end _fbDispatch

    dbg('sending ready');
    // Register dispatch with transport and notify host
    window.__projspecFbDeliver = _fbDispatch;
    _transport.onReady(_fbDispatch);
    vscode.postMessage({ cmd: 'ready' });
})();
