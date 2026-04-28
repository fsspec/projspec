import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';
import {
    getInfo,
    getEnumMembers,
    getLibrary,
    scan,
    createSpec,
    libraryDelete,
    runInTerminal,
    openInFileBrowser,
    urlToPath,
    InfoData,
    LibraryData,
    EnumMembers,
} from './projspec';

/** Default config written when the user picks Configure and no file exists. */
const DEFAULT_CONFIG = {
    scan_types: ['.py', '.yaml', '.yml', '.toml', '.json', '.md'],
    scan_max_files: 100,
    scan_max_size: 5000,
    remote_artifact_status: false,
    capture_artifact_output: true,
    preferred_install_methods: ['conda', 'pip'],
};

/**
 * Entry point webview panel that hosts the two-pane UI: Library on the left
 * and Details on the right.  One panel exists at a time; opening the command
 * while one is already live re-focuses it.
 */
export class ProjspecPanel {
    public static current: ProjspecPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private readonly extensionUri: vscode.Uri;
    private disposables: vscode.Disposable[] = [];
    private info: InfoData | null = null;
    private enums: EnumMembers = {};
    private library: LibraryData = {};
    /**
     * Number of in-flight long-running operations.  The webview spinner is
     * shown iff this is > 0, so composed operations (e.g., scan-then-reload)
     * keep the spinner up continuously instead of flickering off between
     * steps.
     */
    private busyCount = 0;

    public static createOrShow(extensionUri: vscode.Uri): void {
        const col = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
        if (ProjspecPanel.current) {
            ProjspecPanel.current.panel.reveal(col);
            return;
        }
        const panel = vscode.window.createWebviewPanel(
            'projspec.panel',
            'Project Library',
            col,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(extensionUri, 'node_modules', '@fortawesome', 'fontawesome-free'),
                    vscode.Uri.joinPath(extensionUri, 'media'),
                ],
            },
        );
        ProjspecPanel.current = new ProjspecPanel(panel, extensionUri);
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
        this.panel = panel;
        this.extensionUri = extensionUri;

        this.panel.webview.html = this.getHtml();
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
        this.panel.webview.onDidReceiveMessage(
            (msg) => this.onMessage(msg),
            null,
            this.disposables,
        );

        // Kick off the initial load.
        void this.reload(true);
    }

    // ----------------------------------------------------------------------
    //  Message handling
    // ----------------------------------------------------------------------
    private async onMessage(msg: any): Promise<void> {
        try {
            switch (msg.cmd) {
                case 'ready':
                    // webview finished setting up; send current data
                    this.postData();
                    break;
                case 'reload':
                    await this.reload(false);
                    break;
                case 'add':
                    await this.addProject();
                    break;
                case 'configure':
                    await this.configure();
                    break;
                case 'openWith':
                    this.openWith(msg.tool, msg.url);
                    break;
                case 'rescan':
                    await this.rescan(msg.url);
                    break;
                case 'createSpec':
                    await this.createSpecFor(msg.url);
                    break;
                case 'removeFromLibrary':
                    await this.removeFromLibrary(msg.url);
                    break;
                case 'make':
                    this.make(msg.url, msg.spec, msg.artifactType, msg.name);
                    break;
                case 'copyToLocal':
                    vscode.window.showInformationMessage('Copy to local: not implemented');
                    break;
                case 'revealFile':
                    await this.revealFile(msg.fn);
                    break;
                default:
                    console.warn('Unknown message', msg);
            }
        } catch (err) {
            vscode.window.showErrorMessage(`projspec: ${err instanceof Error ? err.message : String(err)}`);
        }
    }

    // ----------------------------------------------------------------------
    //  Busy indicator
    // ----------------------------------------------------------------------
    /**
     * Wrap a promise-returning callback so the webview busy spinner is shown
     * for its entire duration.  Uses a reference count so nested callers
     * (e.g., button handlers that call ``reload``) don't let the spinner
     * flicker off mid-operation.
     */
    private async withBusy<T>(fn: () => Promise<T>): Promise<T> {
        this.busyCount += 1;
        if (this.busyCount === 1) {
            this.panel.webview.postMessage({ type: 'loading', loading: true });
        }
        try {
            return await fn();
        } finally {
            this.busyCount -= 1;
            if (this.busyCount === 0) {
                this.panel.webview.postMessage({ type: 'loading', loading: false });
            }
        }
    }

    // ----------------------------------------------------------------------
    //  Data loading
    // ----------------------------------------------------------------------
    private async reload(initial: boolean): Promise<void> {
        await this.withBusy(async () => {
            try {
                if (initial || !this.info) {
                    this.info = await getInfo();
                    this.enums = await getEnumMembers();
                }
                this.library = await getLibrary();
            } catch (err) {
                vscode.window.showErrorMessage(`projspec: ${err instanceof Error ? err.message : String(err)}`);
            } finally {
                this.postData();
            }
        });
    }

    private postData(): void {
        this.panel.webview.postMessage({
            type: 'data',
            info: this.info,
            enums: this.enums,
            library: this.library,
        });
    }

    // ----------------------------------------------------------------------
    //  Button actions
    // ----------------------------------------------------------------------
    private async addProject(): Promise<void> {
        const picks = await vscode.window.showOpenDialog({
            canSelectFolders: true,
            canSelectFiles: false,
            canSelectMany: false,
            openLabel: 'Add to Library',
        });
        if (!picks || picks.length === 0) {
            return;
        }
        const target = picks[0].fsPath;
        await this.withBusy(async () => {
            const res = await scan(target, true);
            if (res.code !== 0) {
                vscode.window.showWarningMessage(`projspec scan: ${res.stderr.trim() || 'failed'}`);
            }
            await this.reload(false);
        });
    }

    private async configure(): Promise<void> {
        const dir = process.env.PROJSPEC_CONFIG_DIR || path.join(os.homedir(), '.config', 'projspec');
        const file = path.join(dir, 'projspec.json');
        if (!fs.existsSync(file)) {
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(file, JSON.stringify(DEFAULT_CONFIG, null, 4));
        }
        const doc = await vscode.workspace.openTextDocument(file);
        await vscode.window.showTextDocument(doc);
    }

    private openWith(tool: string, url: string): void {
        const p = urlToPath(url);
        switch (tool) {
            case 'vscode':
                runInTerminal(`code ${path.basename(p)}`, 'code', [p]);
                break;
            case 'filebrowser':
                openInFileBrowser(p);
                break;
            case 'pycharm':
                runInTerminal(`pycharm ${path.basename(p)}`, 'pycharm', [p, 'nosplash', 'dontReopenProjects']);
                break;
            case 'jupyter':
                runInTerminal(`jupyter lab ${path.basename(p)}`, 'jupyter', ['lab', p]);
                break;
        }
    }

    private async rescan(url: string): Promise<void> {
        await this.withBusy(async () => {
            const res = await scan(url, true);
            if (res.code !== 0) {
                vscode.window.showWarningMessage(`projspec scan: ${res.stderr.trim() || 'failed'}`);
            }
            await this.reload(false);
        });
    }

    private async createSpecFor(url: string): Promise<void> {
        if (!this.info) {
            vscode.window.showErrorMessage('projspec info not loaded');
            return;
        }
        const project = this.library[url];
        const existing = project ? new Set(Object.keys(project.specs || {})) : new Set<string>();
        const creatable = Object.entries(this.info.specs)
            .filter(([name, entry]) => entry.create && !existing.has(name))
            .map(([name]) => name)
            .sort();
        if (creatable.length === 0) {
            vscode.window.showInformationMessage('No spec types available to create.');
            return;
        }
        const pick = await vscode.window.showQuickPick(creatable, {
            placeHolder: 'Select the type of spec to create',
            matchOnDescription: true,
        });
        if (!pick) {
            return;
        }
        await this.withBusy(async () => {
            const p = urlToPath(url);
            const res = await createSpec(pick, p);
            if (res.code !== 0) {
                vscode.window.showWarningMessage(`projspec create: ${res.stderr.trim() || 'failed'}`);
            }
            // Rescan the specific project, then refresh library.
            await scan(p, true);
            await this.reload(false);
        });
    }

    private async removeFromLibrary(url: string): Promise<void> {
        await this.withBusy(async () => {
            const res = await libraryDelete(url);
            if (res.code !== 0) {
                vscode.window.showWarningMessage(`projspec library delete: ${res.stderr.trim() || 'failed'}`);
            }
            await this.reload(false);
        });
    }

    private make(url: string, spec: string | undefined, artifactType: string, name: string | undefined): void {
        const parts: string[] = [];
        if (spec) {
            parts.push(spec);
        }
        parts.push(artifactType);
        if (name) {
            parts.push(name);
        }
        const artifactArg = parts.join('.');
        const p = urlToPath(url);
        runInTerminal(`projspec make ${artifactArg}`, 'projspec', ['make', artifactArg, p]);
    }

    /**
     * Reveal a file artifact's ``fn`` in the VSCode Explorer.  ``fn`` may
     * contain a glob (commonly ``*`` for wheel names); we expand it and:
     *   - zero matches: show an info toast
     *   - one match: reveal directly
     *   - many matches: let the user pick which one to reveal
     *
     * Only local files are supported - remote artifacts are silently ignored.
     */
    private async revealFile(fn: string): Promise<void> {
        if (!fn || typeof fn !== 'string') { return; }
        // Accept either a plain path or a file:// URI.
        let localFn = fn;
        if (localFn.startsWith('file://')) {
            localFn = localFn.slice('file://'.length);
        }
        // Anything that still looks like a URL with a scheme is not local.
        if (/^[a-z][a-z0-9+.-]*:\/\//i.test(localFn)) {
            vscode.window.showInformationMessage(`Cannot reveal remote file: ${fn}`);
            return;
        }

        const matches = await this.withBusy(() => expandGlob(localFn));
        if (matches.length === 0) {
            vscode.window.showInformationMessage(`No files match: ${fn}`);
            return;
        }
        let target = matches[0];
        if (matches.length > 1) {
            const pick = await vscode.window.showQuickPick(matches, {
                placeHolder: `${matches.length} files match - pick one to reveal`,
            });
            if (!pick) { return; }
            target = pick;
        }
        try {
            await vscode.commands.executeCommand('revealInExplorer', vscode.Uri.file(target));
        } catch (err) {
            vscode.window.showWarningMessage(`Could not reveal ${target}: ${err}`);
        }
    }

    // ----------------------------------------------------------------------
    //  HTML
    // ----------------------------------------------------------------------
    private getHtml(): string {
        const webview = this.panel.webview;
        const faCssUri = webview.asWebviewUri(
            vscode.Uri.joinPath(
                this.extensionUri,
                'node_modules', '@fortawesome', 'fontawesome-free', 'css', 'all.min.css',
            ),
        );
        const nonce = getNonce();
        const csp = [
            `default-src 'none'`,
            `style-src ${webview.cspSource} 'unsafe-inline'`,
            `font-src ${webview.cspSource}`,
            `img-src ${webview.cspSource} data:`,
            `script-src 'nonce-${nonce}'`,
        ].join('; ');

        // Inline the CSS and JS for simplicity - no bundler wired up.
        const css = getPanelCss();
        const js = getPanelJs();

        return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<link rel="stylesheet" href="${faCssUri}" />
<style>${css}</style>
<title>Project Library</title>
</head>
<body>
<div id="app">
    <div id="library">
        <div class="toolbar">
            <button id="btn-add"><i class="fa-solid fa-plus"></i> Add</button>
            <button id="btn-reload"><i class="fa-solid fa-rotate"></i> Reload</button>
            <button id="btn-configure"><i class="fa-solid fa-gear"></i> Configure</button>
        </div>
        <div class="search">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" id="search" placeholder="Filter projects..." />
            <button id="search-clear" title="Clear"><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div id="projects"></div>
        <div id="spinner" class="hidden">
            <i class="fa-solid fa-spinner fa-spin"></i> Loading...
        </div>
    </div>
    <div id="details">
        <div id="details-header">
            <div id="details-title">Details</div>
            <button id="details-toggle" title="Toggle info"><i class="fa-solid fa-chevron-up"></i></button>
        </div>
        <div id="details-info"></div>
        <div id="details-list"></div>
    </div>
</div>
<div id="popup" class="hidden"></div>
<script nonce="${nonce}">${js}</script>
</body>
</html>`;
    }

    // ----------------------------------------------------------------------
    //  Dispose
    // ----------------------------------------------------------------------
    private dispose(): void {
        ProjspecPanel.current = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) { d.dispose(); }
        }
    }
}

function getNonce(): string {
    let text = '';
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return text;
}

/**
 * Expand a glob-ish path (``*`` and ``?`` wildcards, both in filename and
 * directory segments) into a list of matching local files.  Absolute paths
 * are expected; if the path has no wildcards we test it directly.
 */
async function expandGlob(pattern: string): Promise<string[]> {
    if (!/[*?[]/.test(pattern)) {
        try {
            await fs.promises.stat(pattern);
            return [pattern];
        } catch {
            return [];
        }
    }
    // Split on path separators, then walk.
    const isAbsolute = path.isAbsolute(pattern);
    const parts = pattern.split(/[\\/]+/).filter((p, i) => !(i === 0 && p === ''));
    const roots: string[] = [isAbsolute ? (path.sep === '/' ? '/' : parts[0] + path.sep) : '.'];
    const segs = isAbsolute && path.sep !== '/' ? parts.slice(1) : parts;

    let current = roots;
    for (const seg of segs) {
        if (!seg) { continue; }
        const next: string[] = [];
        const segRe = globSegmentToRegex(seg);
        for (const dir of current) {
            let entries: string[];
            try {
                entries = await fs.promises.readdir(dir);
            } catch {
                continue;
            }
            for (const entry of entries) {
                if (segRe.test(entry)) {
                    next.push(path.join(dir, entry));
                }
            }
        }
        current = next;
    }
    return current;
}

function globSegmentToRegex(seg: string): RegExp {
    let re = '^';
    for (const ch of seg) {
        if (ch === '*') { re += '[^/]*'; }
        else if (ch === '?') { re += '[^/]'; }
        else if (/[.+^${}()|\\]/.test(ch)) { re += '\\' + ch; }
        else { re += ch; }
    }
    re += '$';
    return new RegExp(re);
}

// ---------------------------------------------------------------------------
//  Inline resources (CSS + JS) - kept here to avoid a bundler
// ---------------------------------------------------------------------------
function getPanelCss(): string {
    return `
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
/* Subtle kind-based outlines: green for contents (descriptive), red for
   artifacts (actionable outputs).  Uses --vscode-*ForegroundErrorLens-ish
   variables when available but falls back to plain colour values. */
.item-widget.kind-content { border-color: #4ca97a; box-shadow: 0 0 0 1px rgba(76,169,122,0.15); }
.item-widget.kind-artifact { border-color: #c66060; box-shadow: 0 0 0 1px rgba(198,96,96,0.15); }
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
    content: '\\25BE'; position: absolute; left: 0; font-size: 10px; top: 2px;
}
.tree .node.collapsible.collapsed > .label::before { content: '\\25B8'; }
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
    content: ' \\25BE'; font-size: 9px; color: var(--vscode-descriptionForeground);
}
.tree.yaml .yaml-item.collapsible.collapsed > .marker::after,
.tree.yaml .yaml-item.collapsible.collapsed > .label::after { content: ' \\25B8'; }
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
`;
}

function getPanelJs(): string {
    // NOTE: kept as a template string; any \${...} inside needs escaping.
    return PANEL_JS;
}

// The large webview-side script is kept in a separate file-scope constant so
// the bundled extension stays readable.  It runs inside the webview context
// and has no access to vscode/node APIs except through \`acquireVsCodeApi()\`.
//
// We use String.raw so that backslashes in regex literals (e.g. /\/+$/)
// survive the template literal unaltered.  The template must therefore
// still not contain unescaped backticks or \${...} sequences.
const PANEL_JS = String.raw`
(function() {
    const vscode = acquireVsCodeApi();
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
            const stripped = url.replace(/\/+$/, '');
            const idx = stripped.lastIndexOf('/');
            return idx >= 0 ? stripped.slice(idx + 1) : stripped;
        } catch { return url; }
    }
    function specDisplayName(snake) { return snake; }
    function iconForSpec(snake) {
        const entry = info && info.specs && info.specs[snake];
        return entry && entry.icon ? entry.icon : 'cube';
    }
    function iconForContent(snake) {
        const entry = info && info.content && info.content[snake];
        return entry && entry.icon ? entry.icon : 'circle-info';
    }
    function iconForArtifact(snake) {
        const entry = info && info.artifact && info.artifact[snake];
        return entry && entry.icon ? entry.icon : 'cube';
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
        kebabBtn.innerHTML = '<i class="fa-solid fa-ellipsis-vertical"></i>';
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
            chip.innerHTML = '<i class="fa-solid fa-' + icon + '"></i><span>' + escapeHtml(label) + '</span>';
        } else {
            chip.textContent = label;
        }
        chip.addEventListener('click', (ev) => {
            ev.stopPropagation();
            selection = { url, kind, specName };
            // mark active chip + project
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
            // "Open with" sub-items are flattened into the main menu so there
            // is no nested popup to stack above this one.
            addItem(menu, 'Open with VSCode', () => vscode.postMessage({ cmd: 'openWith', tool: 'vscode', url }));
            addItem(menu, 'Open with system filebrowser', () => vscode.postMessage({ cmd: 'openWith', tool: 'filebrowser', url }));
            addItem(menu, 'Open with PyCharm', () => vscode.postMessage({ cmd: 'openWith', tool: 'pycharm', url }));
            addItem(menu, 'Open with jupyter', () => vscode.postMessage({ cmd: 'openWith', tool: 'jupyter', url }));
            addSeparator(menu);
            addItem(menu, 'Rescan', () => vscode.postMessage({ cmd: 'rescan', url }));
            addItem(menu, 'Create spec', () => vscode.postMessage({ cmd: 'createSpec', url }));
            addItem(menu, 'Remove from library', () => vscode.postMessage({ cmd: 'removeFromLibrary', url }));
        } else {
            const ctl = addItem(menu, 'Copy to local', () => vscode.postMessage({ cmd: 'copyToLocal', url }));
            ctl.classList.add('disabled');
            addItem(menu, 'Rescan', () => vscode.postMessage({ cmd: 'rescan', url }));
            addItem(menu, 'Remove from library', () => vscode.postMessage({ cmd: 'removeFromLibrary', url }));
        }
        projectEl.appendChild(menu);
        openKebab = { el: projectEl, menu };
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
        const icon = detailsToggle.querySelector('i');
        if (icon) icon.className = detailsInfo.classList.contains('collapsed') ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up';
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

    /**
     * items is a mapping of typeName -> entry.  The "rich" case is when values
     * carry a 'klass' field (directly, nested, or in an array); each such
     * record becomes its own labelled widget.  If no 'klass' appears anywhere,
     * the whole mapping is rendered as a single untitled YAML widget - that
     * covers content shapes like git_repo's {remotes:[], tags:[], ...}.
     */
    function renderItemGroup(items, kind, showMake, specName) {
        if (!items || typeof items !== 'object') return;
        const keys = Object.keys(items);
        if (keys.length === 0) return;

        if (!hasKlass(items)) {
            // Whole dict is one YAML widget with no title/actions.
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
                // nested by name
                for (const name of Object.keys(entry)) {
                    detailsList.appendChild(makeItemWidget(typeName, name, entry[name], kind, showMake, specName));
                }
            } else {
                // primitive - should not happen in klass-bearing groups, but
                // fall back to a plain widget rather than drop it on the floor.
                detailsList.appendChild(makePlainWidget({ [typeName]: entry }));
            }
        }
    }

    /** Recursively check whether the object/array contains any 'klass' key. */
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
        title.innerHTML = '<i class="fa-solid fa-' + iconName + '"></i> ' + escapeHtml(klass) + (name ? ' <span class="widget-subtitle">- ' + escapeHtml(name) + '</span>' : '');
        w.appendChild(title);

        const actions = document.createElement('div');
        actions.className = 'widget-actions';

        // "=>" reveal button: shown when the artifact has a local fn field.
        // A value with an explicit non-file:// URL scheme is treated as remote.
        const fn = (data && typeof data === 'object') ? data.fn : undefined;
        if (kind === 'artifact' && typeof fn === 'string' && fn.length > 0 && isLocalPath(fn)) {
            const rv = document.createElement('button');
            rv.title = 'Reveal ' + fn + ' in Explorer';
            rv.innerHTML = '<i class="fa-solid fa-arrow-right-long"></i>';
            rv.addEventListener('click', (e) => {
                e.stopPropagation();
                vscode.postMessage({ cmd: 'revealFile', fn });
            });
            actions.appendChild(rv);
        }

        if (showMake) {
            const mk = document.createElement('button');
            mk.title = 'Make';
            mk.innerHTML = '<i class="fa-solid fa-play"></i>';
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
        ib.innerHTML = '<i class="fa-solid fa-circle-info"></i>';
        ib.addEventListener('click', (e) => {
            e.stopPropagation();
            showInfoPopup(klass, kind, e.clientX, e.clientY);
        });
        actions.appendChild(ib);
        w.appendChild(actions);

        // YAML tree
        const tree = document.createElement('div');
        tree.className = 'tree yaml';
        tree.appendChild(renderYaml(stripKlass(data)));
        w.appendChild(tree);

        return w;
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
    //
    // Rules:
    //   - Dicts render as "key: value" pairs, one per line, with nested
    //     objects indented one level.
    //   - Lists render each item on its own line prefixed with "- ", with no
    //     index numbers and no surrounding brackets.
    //   - Strings render without quotes.
    //   - Enum objects ({klass:['enum', name], value}) render as their member
    //     label (e.g. "CONDA" instead of "2"); if no enum map is available,
    //     fall back to the raw value.

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
            // Nested container: render inline header on the marker line then
            // indent the children below.
            node.classList.add('collapsible');
            node.appendChild(marker);
            // No inline summary; children come below.
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
            // YAML: no quotes around strings
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

    /** True if 'p' names a local file (has no scheme, or uses file://). */
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
        // First position off-screen to measure, then place to the left of cursor.
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

    // ----- toolbar -----
    document.getElementById('btn-add').addEventListener('click', () => vscode.postMessage({ cmd: 'add' }));
    document.getElementById('btn-reload').addEventListener('click', () => vscode.postMessage({ cmd: 'reload' }));
    document.getElementById('btn-configure').addEventListener('click', () => vscode.postMessage({ cmd: 'configure' }));
    searchEl.addEventListener('input', () => render());
    searchClear.addEventListener('click', () => { searchEl.value = ''; render(); });

    // ----- message bus -----
    window.addEventListener('message', (ev) => {
        const msg = ev.data;
        if (msg.type === 'loading') {
            spinnerEl.classList.toggle('hidden', !msg.loading);
        } else if (msg.type === 'data') {
            info = msg.info;
            enums = msg.enums || {};
            library = msg.library || {};
            // Drop selection if its target disappeared.
            if (selection && !library[selection.url]) selection = null;
            render();
        }
    });
    vscode.postMessage({ cmd: 'ready' });
})();
`;
