/**
 * CombinedPanel — a single VS Code webview panel hosting both the
 * Project Library and the File Browser as switchable tabs.
 *
 * Cross-tab interactions
 * ─────────────────────
 * • "Add to library" in the File Browser → after success the host reloads
 *   the Project Library and selects the newly added URL.
 * • "Open with system filebrowser" in the Library → switches to the File
 *   Browser tab and navigates to that URL (with any storage_options).
 */

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
    urlToPath,
    runProjspec,
    parseJsonOutput,
    InfoData,
    LibraryData,
    EnumMembers,
} from './projspec';
import { getFileBrowserCss, getFileBrowserJs } from './fileBrowserPanel';

// Prefer shared webui filebrowser assets if present; fall back to the TS-embedded copies.
function _readWebuiFile(name: string): string | null {
    try {
        const p = path.resolve(__dirname, '..', '..', 'src', 'projspec', 'webui', name);
        return fs.readFileSync(p, 'utf-8');
    } catch { return null; }
}
function getSharedFbCss(): string { return _readWebuiFile('filebrowser.css') ?? getFileBrowserCss(); }
function getSharedFbJs():  string { return _readWebuiFile('filebrowser.js')  ?? getFileBrowserJs();  }
function getSharedTabsCss(): string { return _readWebuiFile('tabs.css') ?? ''; }
function getSharedTabsJs():  string { return _readWebuiFile('tabs.js')  ?? ''; }
import { ServerClient, fbCall } from './serverClient';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function basenameOf(url: string): string {
    return url.replace(/\/+$/, '').split('/').pop() || url;
}

function getNonce(): string {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    return Array.from({ length: 32 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

const DEFAULT_CONFIG = {
    scan_types: ['.py', '.yaml', '.yml', '.toml', '.json', '.md'],
    scan_max_files: 100,
    scan_max_size: 5000,
    remote_artifact_status: false,
    capture_artifact_output: true,
    preferred_install_methods: ['conda', 'pip'],
};

// ---------------------------------------------------------------------------
// File-based logger — mirrors pycharm_plugin PluginLogger.
// Writes to <projspec-config-dir>/vscode.log (appended, never truncated).
// ---------------------------------------------------------------------------

function _logFilePath(): string {
    const dir = process.env['PROJSPEC_CONFIG_DIR'] || path.join(os.homedir(), '.config', 'projspec');
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, 'vscode.log');
}

function log(msg: string): void {
    const ts = new Date().toISOString().replace('T', ' ').replace('Z', '');
    const line = `${ts} [INFO] ${msg}\n`;
    try { fs.appendFileSync(_logFilePath(), line, 'utf-8'); } catch { /* best-effort */ }
}

async function expandGlob(pattern: string): Promise<string[]> {
    if (!/[*?[]/.test(pattern)) {
        try { await fs.promises.stat(pattern); return [pattern]; } catch { return []; }
    }
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
            try { entries = await fs.promises.readdir(dir); } catch { continue; }
            for (const entry of entries) {
                if (segRe.test(entry)) { next.push(path.join(dir, entry)); }
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
// CombinedPanel
// ---------------------------------------------------------------------------

export class CombinedPanel {
    public static current: CombinedPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private readonly extensionUri: vscode.Uri;
    private disposables: vscode.Disposable[] = [];

    // Library state
    private info: InfoData | null = null;
    private enums: EnumMembers = {};
    private library: LibraryData = {};
    private libBusyCount = 0;

    // File browser state
    private fbBusyCount = 0;
    private fbPendingInit: {
        bookmarks: unknown[];
        protocols: string[];
        libraryUrls: string[];
        startUrl: string;
    } | null = null;
    private fbReadyReceived = false;
    private _openedRemoteFiles = new Map<string, { url: string; storageOptions: string }>();

    // ---------------------------------------------------------------------------
    // Factory
    // ---------------------------------------------------------------------------
    public static createOrShow(
        extensionUri: vscode.Uri,
        initialTab?: 'library' | 'filebrowser',
        initialUrl?: string,
    ): void {
        const col = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
        if (CombinedPanel.current) {
            CombinedPanel.current.panel.reveal(col);
            if (initialTab) {
                CombinedPanel.current.switchTab(initialTab, initialUrl);
            }
            return;
        }
        const panel = vscode.window.createWebviewPanel(
            'projspec.combined',
            'projspec',
            col,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')],
            },
        );
        CombinedPanel.current = new CombinedPanel(panel, extensionUri, initialTab, initialUrl);
    }

    private constructor(
        panel: vscode.WebviewPanel,
        extensionUri: vscode.Uri,
        initialTab?: 'library' | 'filebrowser',
        initialUrl?: string,
    ) {
        this.panel = panel;
        this.extensionUri = extensionUri;

        this.panel.webview.html = this.getHtml(initialTab || 'library');
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
        this.panel.webview.onDidReceiveMessage(
            (msg) => void this.onMessage(msg),
            null,
            this.disposables,
        );

        // Start both panels initialising in parallel
        void this.fbPrefetchInit(initialTab === 'filebrowser' ? initialUrl : undefined);
        void this.libReload(true);
    }

    // ---------------------------------------------------------------------------
    // Tab switching (host-initiated)
    // ---------------------------------------------------------------------------
    public switchTab(tab: 'library' | 'filebrowser', url?: string): void {
        this.panel.webview.postMessage({ type: 'switchTab', tab });
        if (tab === 'filebrowser' && url) {
            void this.fbWithBusy(() => this.fbBrowse(url, undefined, false));
        }
    }

    // ---------------------------------------------------------------------------
    // Unified message dispatcher
    // ---------------------------------------------------------------------------
    private async onMessage(msg: any): Promise<void> {
        try {
            if (msg.tab === 'fb') {
                await this.onFbMessage(msg);
            } else {
                // library (or legacy messages without tab field)
                await this.onLibMessage(msg);
            }
        } catch (err) {
            vscode.window.showErrorMessage(
                `projspec: ${err instanceof Error ? err.message : String(err)}`,
            );
        }
    }

    // =========================================================================
    // LIBRARY TAB
    // =========================================================================

    private async onLibMessage(msg: any): Promise<void> {
        switch (msg.cmd) {
            case 'ready':
                this.libPostData();
                break;
            case 'reload':
                await this.libReload(false);
                break;
            case 'add':
                await this.libAddProject();
                break;
            case 'addAdvanced':
                await this.libAddProjectAdvanced(msg.path, msg.storageOptions);
                break;
            case 'configure':
                await this.libConfigure();
                break;
            case 'openWith':
                this.libOpenWith(msg.tool, msg.url);
                break;
            case 'rescan':
                await this.libRescan(msg.url);
                break;
            case 'createSpec':
                await this.libCreateSpecFor(msg.url);
                break;
            case 'createSpecConfirmed':
                await this.libCreateSpecConfirmed(msg.url, msg.spec);
                break;
            case 'removeFromLibrary':
                await this.libRemoveFromLibrary(msg.url);
                break;
            case 'make':
                this.libMake(msg.url, msg.spec, msg.artifactType, msg.name);
                break;
            case 'copyToLocal':
                vscode.window.showInformationMessage('Copy to local: not implemented');
                break;
            case 'revealFile':
                await this.libRevealFile(msg.fn);
                break;
            default:
                console.warn('[CombinedPanel] Unknown lib message', msg);
        }
    }

    private async libWithBusy<T>(fn: () => Promise<T>): Promise<T> {
        this.libBusyCount += 1;
        if (this.libBusyCount === 1) {
            this.panel.webview.postMessage({ type: 'loading', tab: 'library', loading: true });
        }
        try {
            return await fn();
        } finally {
            this.libBusyCount -= 1;
            if (this.libBusyCount === 0) {
                this.panel.webview.postMessage({ type: 'loading', tab: 'library', loading: false });
            }
        }
    }

    private async libReload(initial: boolean, selectUrl?: string): Promise<void> {
        await this.libWithBusy(async () => {
            try {
                const client = ServerClient.get();
                if (initial || !this.info) {
                    // Try server first, fall back to subprocess helpers
                    const infoData = await client.info();
                    const enumData = await client.enumMembers();
                    this.info = (infoData ?? await getInfo()) as InfoData;
                    this.enums = (enumData ?? await getEnumMembers()) as EnumMembers;
                }
                const libData = await client.libraryList();
                this.library = (libData ?? await getLibrary()) as LibraryData;
            } catch (err) {
                vscode.window.showErrorMessage(
                    `projspec: ${err instanceof Error ? err.message : String(err)}`,
                );
            } finally {
                this.libPostData(selectUrl);
            }
        });
    }

    private libPostData(selectUrl?: string): void {
        this.panel.webview.postMessage({
            type: 'data',
            tab: 'library',
            info: this.info,
            enums: this.enums,
            library: this.library,
            ...(selectUrl ? { selectUrl } : {}),
        });
    }

    private async libAddProject(): Promise<void> {
        const picks = await vscode.window.showOpenDialog({
            canSelectFolders: true,
            canSelectFiles: false,
            canSelectMany: false,
            openLabel: 'Add to Library',
        });
        if (!picks || picks.length === 0) { return; }
        const target = picks[0].fsPath;
        await this.libWithBusy(async () => {
            const result = await ServerClient.get().scan(target, true);
            if (result === null) {
                // Fall back to subprocess
                const res = await scan(target, true);
                if (res.code !== 0) {
                    vscode.window.showWarningMessage(`projspec scan: ${res.stderr.trim() || 'failed'}`);
                }
            }
            await this.libReload(false);
        });
    }

    private async libAddProjectAdvanced(pathOrPattern: string, storageOptions: string): Promise<void> {
        await this.libWithBusy(async () => {
            const result = await ServerClient.get().scan(pathOrPattern, true, storageOptions || undefined);
            if (result === null) {
                const res = await scan(pathOrPattern, true, storageOptions || undefined);
                if (res.code !== 0) {
                    vscode.window.showWarningMessage(`projspec scan: ${res.stderr.trim() || 'failed'}`);
                }
            }
            await this.libReload(false);
        });
    }

    private async libConfigure(): Promise<void> {
        const dir = process.env.PROJSPEC_CONFIG_DIR || path.join(os.homedir(), '.config', 'projspec');
        const file = path.join(dir, 'projspec.json');
        if (!fs.existsSync(file)) {
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(file, JSON.stringify(DEFAULT_CONFIG, null, 4));
        }
        const doc = await vscode.workspace.openTextDocument(file);
        await vscode.window.showTextDocument(doc);
        vscode.window.showInformationMessage(
            'ProjSpec configuration — see the docs for all available fields.',
            'Open docs',
        ).then((choice) => {
            if (choice === 'Open docs') {
                vscode.env.openExternal(
                    vscode.Uri.parse('https://projspec.readthedocs.io/en/latest/config.html'),
                );
            }
        });
    }

    /**
     * "Open with system filebrowser" now switches to the File Browser tab
     * and navigates to the project URL (with its stored storage_options).
     * All other "Open with …" tools continue to work as before.
     */
    private libOpenWith(tool: string, url: string): void {
        if (tool === 'filebrowser') {
            // Get the storage options for this library entry, if any
            const soStr = this.libEntryStorageOptions(url);
            // Switch tab; navigate to the URL root
            this.panel.webview.postMessage({ type: 'switchTab', tab: 'filebrowser' });
            void this.fbWithBusy(() => this.fbBrowse(url, soStr, false));
            return;
        }
        const p = urlToPath(url);
        switch (tool) {
            case 'vscode':
                runInTerminal(`code ${path.basename(p)}`, 'code', [p]);
                break;
            case 'pycharm':
                runInTerminal(`pycharm ${path.basename(p)}`, 'pycharm', [p, 'nosplash', 'dontReopenProjects']);
                break;
            case 'jupyter':
                runInTerminal(`jupyter lab ${path.basename(p)}`, 'jupyter', ['lab', p]);
                break;
        }
    }

    private libEntryStorageOptions(url: string): string | undefined {
        const so = this.library[url]?.storage_options;
        if (so && typeof so === 'object' && Object.keys(so).length > 0) {
            return JSON.stringify(so);
        }
        return undefined;
    }

    private async libRescan(url: string): Promise<void> {
        await this.libWithBusy(async () => {
            const soStr = this.libEntryStorageOptions(url);
            const result = await ServerClient.get().scan(url, true, soStr);
            if (result === null) {
                const res = await scan(url, true, soStr);
                if (res.code !== 0) {
                    vscode.window.showWarningMessage(`projspec scan: ${res.stderr.trim() || 'failed'}`);
                }
            }
            await this.libReload(false);
        });
    }

    private async libCreateSpecFor(url: string): Promise<void> {
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
        this.panel.webview.postMessage({
            type: 'openCreateSpecModal',
            tab: 'library',
            url,
            specs: creatable,
        });
    }

    private async libCreateSpecConfirmed(url: string, spec: string): Promise<void> {
        await this.libWithBusy(async () => {
            const p = urlToPath(url);
            const soStr = this.libEntryStorageOptions(url);
            // Create the spec file
            const createResult = await ServerClient.get().create(spec, p);
            if (createResult === null) {
                const res = await createSpec(spec, p);
                if (res.code !== 0) {
                    vscode.window.showWarningMessage(`projspec create: ${res.stderr.trim() || 'failed'}`);
                }
            }
            // Rescan and reload
            await ServerClient.get().scan(p, true, soStr) ?? await scan(p, true, soStr);
            await this.libReload(false);
        });
    }

    private async libRemoveFromLibrary(url: string): Promise<void> {
        await this.libWithBusy(async () => {
            const result = await ServerClient.get().libraryDelete(url);
            if (result === null) {
                const res = await libraryDelete(url);
                if (res.code !== 0) {
                    vscode.window.showWarningMessage(`projspec library delete: ${res.stderr.trim() || 'failed'}`);
                }
            }
            await this.libReload(false);
        });
    }

    private libMake(url: string, spec: string | undefined, artifactType: string, name: string | undefined): void {
        const parts: string[] = [];
        if (spec) { parts.push(spec); }
        parts.push(artifactType);
        if (name) { parts.push(name); }
        const artifactArg = parts.join('.');
        const p = urlToPath(url);
        runInTerminal(`projspec make ${artifactArg}`, 'projspec', ['make', artifactArg, p]);
    }

    private async libRevealFile(fn: string): Promise<void> {
        if (!fn || typeof fn !== 'string') { return; }
        let localFn = fn;
        if (localFn.startsWith('file://')) { localFn = localFn.slice('file://'.length); }
        if (/^[a-z][a-z0-9+.-]*:\/\//i.test(localFn)) {
            vscode.window.showInformationMessage(`Cannot reveal remote file: ${fn}`);
            return;
        }
        const matches = await this.libWithBusy(() => expandGlob(localFn));
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

    // =========================================================================
    // FILE BROWSER TAB
    // =========================================================================

    private async onFbMessage(msg: Record<string, unknown>): Promise<void> {
        const cmd = msg.cmd as string;
        switch (cmd) {
            case 'ready':
                this.fbReadyReceived = true;
                if (this.fbPendingInit) { void this.fbSendInitialData(); }
                break;
            case 'browse':
                await this.fbWithBusy(() =>
                    this.fbBrowse(msg.url as string, msg.storageOptions as string | undefined, msg.push !== false),
                );
                break;
            case 'inspect':
                await this.fbWithBusy(() =>
                    this.fbInspect(msg.url as string, msg.storageOptions as string | undefined),
                );
                break;
            case 'openFile':
                await this.fbOpenFileInEditor(
                    msg.url as string,
                    msg.storageOptions as string | undefined,
                    msg.maxBytes as number | undefined,
                );
                break;
            case 'writeFile':
                await this.fbWriteFile(msg.url as string, msg.content as string, msg.storageOptions as string | undefined);
                break;
            case 'createFile':
                await this.fbCreateFile(msg.parentUrl as string, msg.name as string, msg.storageOptions as string | undefined);
                break;
            case 'deleteEntry':
                await this.fbDeleteEntry(msg.url as string, msg.isDir as boolean, msg.storageOptions as string | undefined);
                break;
            case 'deleteEntries':
                await this.fbDeleteEntries(
                    msg.items as { url: string; isDir: boolean; storageOptions?: string }[],
                );
                break;
            case 'renameEntry':
                await this.fbRenameEntry(msg.url as string, msg.newName as string, msg.storageOptions as string | undefined);
                break;
            case 'paste':
                await this.fbPasteEntry(
                    msg.items as { src: string; srcStorageOptions?: string }[],
                    msg.dstDir as string,
                    msg.dstStorageOptions as string | undefined,
                    msg.mode as string,
                    (msg.confirmed as boolean | undefined) ?? false,
                );
                break;
            case 'mkdir':
                await this.fbMkdirEntry(msg.parentUrl as string, msg.name as string, msg.storageOptions as string | undefined);
                break;
            case 'addBookmark':
                await this.fbBookmarkAdd(
                    msg.url as string,
                    msg.label as string | undefined,
                    msg.storageOptions as string | undefined,
                );
                break;
            case 'removeBookmark':
                await this.fbBookmarkRemove(msg.url as string);
                break;
            case 'addToLibrary':
                await this.fbAddToLibrary(msg.url as string, msg.storageOptions as string | undefined);
                break;
            case 'scanDir':
                await this.fbWithBusy(() =>
                    this.fbScanDir(msg.url as string, msg.storageOptions as string | undefined),
                );
                break;
            case 'expandDir':
                void this.fbExpandDir(msg.url as string, msg.storageOptions as string | undefined);
                break;
            case 'goToUrl':
                await this.fbWithBusy(() =>
                    this.fbGoToUrl(msg.url as string, msg.storageOptions as string | undefined),
                );
                break;
            case 'log':
                log('[fb] ' + (msg.msg as string));
                break;
            default:
                log('unknown fb cmd: ' + cmd);
                console.warn('[CombinedPanel] Unknown fb cmd:', cmd);
        }
    }

    /** Post a message tagged for the filebrowser tab. */
    private fbPost(msg: Record<string, unknown>): void {
        this.panel.webview.postMessage({ ...msg, tab: 'filebrowser' });
    }

    private fbWithBusy<T>(fn: () => Promise<T>): Promise<T> {
        this.fbBusyCount += 1;
        if (this.fbBusyCount === 1) { this.fbPost({ type: 'loading', loading: true }); }
        return fn().finally(() => {
            this.fbBusyCount -= 1;
            if (this.fbBusyCount === 0) { this.fbPost({ type: 'loading', loading: false }); }
        });
    }

    private async fbPrefetchInit(startUrl?: string): Promise<void> {
        const client = ServerClient.get();
        let bookmarks: unknown[] = [];
        let protocols: string[] = [];
        let libraryUrls: string[] = [];
        try {
            const bms = await fbCall('bookmarks_list', {});
            if (Array.isArray(bms.data)) { bookmarks = bms.data; }
        } catch (e) { log('bookmarks_list error: ' + e); }
        try {
            const proto = await fbCall('supported_protocols', {});
            if (Array.isArray(proto.data)) { protocols = proto.data as string[]; }
        } catch (e) { log('supported_protocols error: ' + e); }
        try {
            const libData = await client.libraryList() as Record<string, unknown> | null;
            if (libData) {
                libraryUrls = Object.keys(libData);
            } else {
                const libRes = await runProjspec(['library', 'list', '--json-out']);
                if (libRes.code === 0) {
                    libraryUrls = Object.keys(parseJsonOutput(libRes.stdout) as Record<string, unknown>);
                }
            }
        } catch (e) { log('library list error: ' + e); }
        this.fbPendingInit = {
            bookmarks,
            protocols,
            libraryUrls,
            startUrl: startUrl || os.homedir(),
        };
        if (this.fbReadyReceived) { void this.fbSendInitialData(); }
    }

    private async fbSendInitialData(): Promise<void> {
        const init = this.fbPendingInit;
        if (!init) { return; }
        this.fbPendingInit = null;
        await this.fbWithBusy(async () => {
            this.fbPost({ type: 'init', bookmarks: init.bookmarks, protocols: init.protocols, libraryUrls: init.libraryUrls });
            await this.fbBrowse(init.startUrl, undefined, false);
        });
    }

    private async fbBrowse(url: string, storageOptions: string | undefined, pushHistory: boolean): Promise<void> {
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const res = await fbCall('browse', so ? { url, storage_options: so } : { url });
        const data = (res.data as Record<string, unknown>) || {
            url, entries: [], parent: null, protocol: '',
            error: res.stderr || `exit ${res.code}`,
        };
        this.fbPost({ type: 'browseResult', pushHistory, storageOptions: storageOptions || '', ...data });
    }

    private async fbInspect(url: string, storageOptions: string | undefined): Promise<void> {
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const res = await fbCall('inspect_as_project', so ? { url, storage_options: so } : { url });
        const data = (res.data as Record<string, unknown>) || { url, error: res.stderr || `exit ${res.code}` };
        this.fbPost({ type: 'inspectResult', ...data });

        const client = ServerClient.get();
        const [infoResult, enumsResult] = await Promise.all([
            client.info(),
            client.enumMembers(),
        ]);

        this.fbPost({
            type: 'projectScanned',
            url,
            project: data['project'] || null,
            error: data['error'] || null,
            text_preview: data['text_preview'] || null,
            info: infoResult || {},
            enums: enumsResult || {},
        });
    }

    private async fbOpenFileInEditor(url: string, storageOptions: string | undefined, maxBytes?: number): Promise<void> {
        await this.fbWithBusy(async () => {
            if (url.startsWith('file://') || !url.includes('://')) {
                const localPath = url.startsWith('file://') ? url.slice('file://'.length) : url;
                const doc = await vscode.workspace.openTextDocument(localPath);
                await vscode.window.showTextDocument(doc);
                return;
            }
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('read_file', so
                ? { url, storage_options: so, ...(maxBytes ? { max_bytes: maxBytes } : {}) }
                : { url, ...(maxBytes ? { max_bytes: maxBytes } : {}) });
            const data = res.data as Record<string, unknown>;
            if (!data || data['error']) {
                throw new Error((data?.['error'] as string) || res.stderr || 'Failed to read file');
            }
            const ext = path.extname(url) || '.txt';
            const tmpFile = path.join(os.tmpdir(), `projspec_fb_${Date.now()}${ext}`);
            fs.writeFileSync(tmpFile, (data['content'] as string) || '', 'utf-8');
            const doc = await vscode.workspace.openTextDocument(tmpFile);
            await vscode.window.showTextDocument(doc);
            this._openedRemoteFiles.set(tmpFile, { url, storageOptions: storageOptions || '' });
            const sub = vscode.workspace.onDidSaveTextDocument(async (saved) => {
                if (saved.fileName === tmpFile) {
                    await this.fbPushRemoteFile(tmpFile, url, storageOptions);
                }
            });
            this.disposables.push(sub);
        });
    }

    private async fbPushRemoteFile(tmpFile: string, remoteUrl: string, storageOptions: string | undefined): Promise<void> {
        const content = fs.readFileSync(tmpFile, 'utf-8');
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const res = await fbCall('write_file', so
            ? { url: remoteUrl, content, storage_options: so }
            : { url: remoteUrl, content });
        const data = res.data as Record<string, unknown>;
        if (data?.['error']) { vscode.window.showErrorMessage(`Save failed: ${data['error']}`); }
        else { vscode.window.showInformationMessage(`Saved to ${remoteUrl}`); }
    }

    private async fbWriteFile(url: string, content: string, storageOptions: string | undefined): Promise<void> {
        await this.fbWithBusy(async () => {
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('write_file', so ? { url, content, storage_options: so } : { url, content });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) { throw new Error(data['error'] as string); }
            const parent = url.replace(/\/?[^/]+$/, '') || '/';
            await this.fbBrowse(parent, storageOptions, false);
        });
    }

    private async fbCreateFile(parentUrl: string, name: string, storageOptions: string | undefined): Promise<void> {
        await this.fbWithBusy(async () => {
            const newUrl = parentUrl.replace(/\/$/, '') + '/' + name;
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('write_file', so
                ? { url: newUrl, content: '', storage_options: so }
                : { url: newUrl, content: '' });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) { throw new Error(data['error'] as string); }
            await this.fbBrowse(parentUrl, storageOptions, false);
        });
    }

    private async fbDeleteEntry(url: string, isDir: boolean, storageOptions: string | undefined): Promise<void> {
        const label = url.split('/').pop() || url;
        const confirm = await vscode.window.showWarningMessage(`Delete "${label}"?`, { modal: true }, 'Delete');
        if (confirm !== 'Delete') { return; }
        await this.fbWithBusy(async () => {
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('delete', so
                ? { url, recursive: isDir, storage_options: so }
                : { url, recursive: isDir });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) { throw new Error(data['error'] as string); }
            const parent = url.replace(/\/?[^/]+$/, '') || '/';
            await this.fbBrowse(parent, storageOptions, false);
        });
    }

    /**
     * Delete one or more entries (multi-select). Shows a single confirm
     * dialog for the whole batch, then deletes each item and reports
     * per-item results so partial failures are visible.
     */
    private async fbDeleteEntries(
        items: { url: string; isDir: boolean; storageOptions?: string }[],
    ): Promise<void> {
        if (!items.length) { return; }
        const label = items.length === 1
            ? (items[0].url.split('/').pop() || items[0].url)
            : `${items.length} items`;
        const confirm = await vscode.window.showWarningMessage(`Delete ${label}?`, { modal: true }, 'Delete');
        if (confirm !== 'Delete') { return; }
        await this.fbWithBusy(async () => {
            const results: { url: string; error: string | null }[] = [];
            let refreshDir: string | undefined;
            for (const item of items) {
                const so = item.storageOptions ? JSON.parse(item.storageOptions) : null;
                const res = await fbCall('delete', so
                    ? { url: item.url, recursive: item.isDir, storage_options: so }
                    : { url: item.url, recursive: item.isDir });
                const data = (res.data as Record<string, unknown>) || { error: res.stderr || `exit ${res.code}` };
                results.push({ url: item.url, error: (data['error'] as string) || null });
                refreshDir = item.url.replace(/\/?[^/]+$/, '') || '/';
            }
            this.fbPost({ type: 'deleteEntriesResult', results });
            if (refreshDir) { await this.fbBrowse(refreshDir, items[0].storageOptions, false); }
        });
    }

    private async fbRenameEntry(url: string, newName: string, storageOptions: string | undefined): Promise<void> {
        await this.fbWithBusy(async () => {
            const parent = url.replace(/\/?[^/]+$/, '') || '/';
            const dst = parent.replace(/\/$/, '') + '/' + newName;
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('move', so
                ? { src: url, dst, storage_options: so }
                : { src: url, dst });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) { throw new Error(data['error'] as string); }
            await this.fbBrowse(parent, storageOptions, false);
        });
    }

    /**
     * Paste one or more previously copied/cut entries into `dstDir`.
     * `mode` is 'copy' or 'cut' — 'cut' maps to `move()` per item; 'copy'
     * first checks the aggregate size of all items via `total_size()` (a
     * single call rather than one per item) and, if it exceeds the
     * configured threshold and `confirmed` is not set, reports
     * `pasteNeedsConfirm` back to the webview instead of copying anything.
     * Once confirmed (or under the threshold), each item is copied/moved
     * individually and per-item results are reported so partial failures
     * are visible.
     */
    /**
     * Paste one or more previously copied/cut entries into `dstDir`.
     * `mode` is 'copy' or 'cut' — 'cut' maps to `move()` per item; 'copy'
     * first checks the *aggregate* size of all items via a single
     * `total_size()` call (which reports `needs_confirm` using the same
     * `filebrowser_copy_confirm_bytes` threshold `copy()` itself enforces).
     * If confirmation is needed and `confirmed` wasn't already set, nothing
     * is copied yet — `pasteNeedsConfirm` is reported back to the webview,
     * which re-sends this same message with `confirmed: true` once the user
     * accepts. Once confirmed (or under the threshold), each item is
     * copied/moved individually — passing `confirmed: true` through so the
     * per-item calls don't redundantly re-check a threshold we've already
     * cleared for the batch — and per-item results are reported so partial
     * failures are visible.
     */
    private async fbPasteEntry(
        items: { src: string; srcStorageOptions?: string }[],
        dstDir: string,
        dstStorageOptions: string | undefined,
        mode: string,
        confirmed: boolean,
    ): Promise<void> {
        if (!items.length) { return; }
        await this.fbWithBusy(async () => {
            const soStr = items[0].srcStorageOptions || dstStorageOptions;
            const so = soStr ? JSON.parse(soStr) : null;
            const fn = mode === 'cut' ? 'move' : 'copy';

            if (fn === 'copy' && !confirmed) {
                const urls = items.map((it) => it.src);
                const tsRes = await fbCall('total_size', so ? { urls, storage_options: so } : { urls });
                const tsData = (tsRes.data as Record<string, unknown>) || {};
                if (tsData['needs_confirm']) {
                    this.fbPost({
                        type: 'pasteNeedsConfirm',
                        items, dstDir, dstStorageOptions, mode,
                        totalSize: tsData['total_size'],
                    });
                    return;
                }
            }

            const results: { src: string; dst: string; error: string | null }[] = [];
            for (const item of items) {
                const itemSoStr = item.srcStorageOptions || dstStorageOptions;
                const itemSo = itemSoStr ? JSON.parse(itemSoStr) : so;
                const dst = dstDir.replace(/\/$/, '') + '/' + basenameOf(item.src);
                const kwargs: Record<string, unknown> = itemSo
                    ? { src: item.src, dst, storage_options: itemSo }
                    : { src: item.src, dst };
                if (fn === 'copy') { kwargs['confirmed'] = true; }
                const res = await fbCall(fn, kwargs);
                const data = (res.data as Record<string, unknown>) || { error: res.stderr || `exit ${res.code}` };
                results.push({ src: item.src, dst, error: (data['error'] as string) || null });
            }
            this.fbPost({ type: 'pasteResult', mode, results, error: null });
        });
    }

    private async fbMkdirEntry(parentUrl: string, name: string, storageOptions: string | undefined): Promise<void> {
        await this.fbWithBusy(async () => {
            const newUrl = parentUrl.replace(/\/$/, '') + '/' + name;
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('mkdir', so ? { url: newUrl, storage_options: so } : { url: newUrl });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) { throw new Error(data['error'] as string); }
            await this.fbBrowse(parentUrl, storageOptions, false);
        });
    }

    private async fbBookmarkAdd(url: string, label?: string, storageOptions?: string): Promise<void> {
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const kwargs: Record<string, unknown> = { url };
        if (label) { kwargs['label'] = label; }
        if (so) { kwargs['storage_options'] = so; }
        const res = await fbCall('bookmark_add', kwargs);
        const bms = Array.isArray(res.data) ? res.data : [];
        this.fbPost({ type: 'bookmarksUpdated', bookmarks: bms });
    }

    private async fbBookmarkRemove(url: string): Promise<void> {
        const res = await fbCall('bookmark_remove', { url });
        const bms = Array.isArray(res.data) ? res.data : [];
        this.fbPost({ type: 'bookmarksUpdated', bookmarks: bms });
    }

    /**
     * After adding a directory to the library from the File Browser tab:
     * 1. Refresh the filebrowser's library URL set (icon update).
     * 2. Reload the Library tab and select the newly added URL.
     */
    private async fbAddToLibrary(url: string, storageOptions: string | undefined): Promise<void> {
        await this.fbWithBusy(async () => {
            const so = storageOptions ? JSON.parse(storageOptions) : null;
            const res = await fbCall('add_to_projspec_library', so ? { url, storage_options: so } : { url });
            const data = res.data as Record<string, unknown>;
            if (data?.['error']) {
                vscode.window.showWarningMessage(`Add to library: ${data['error']}`);
            } else {
                vscode.window.showInformationMessage(`Added to projspec library: ${url}`);
                // Update filebrowser library badge icons
                const client = ServerClient.get();
                try {
                    const libData = await client.libraryList() as Record<string, unknown> | null;
                    if (libData) {
                        this.fbPost({ type: 'libraryUrlsUpdated', libraryUrls: Object.keys(libData) });
                    } else {
                        const libRes = await runProjspec(['library', 'list', '--json-out']);
                        if (libRes.code === 0) {
                            const ld = parseJsonOutput(libRes.stdout) as Record<string, unknown>;
                            this.fbPost({ type: 'libraryUrlsUpdated', libraryUrls: Object.keys(ld) });
                        }
                    }
                } catch { /* ok */ }
                // Reload the library tab, highlight the new entry, and switch to it
                await this.libReload(false, url);
                this.panel.webview.postMessage({ type: 'switchTab', tab: 'library' });
            }
        });
    }

    private async fbGoToUrl(url: string, storageOptions: string | undefined): Promise<void> {
        await this.fbBrowse(url, storageOptions, true);
    }

    private async fbExpandDir(url: string, storageOptions: string | undefined): Promise<void> {
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const res = await fbCall('browse', so ? { url, storage_options: so } : { url });
        const data = (res.data as Record<string, unknown>) || {
            url, entries: [], parent: null, protocol: '',
            error: res.stderr || `exit ${res.code}`,
        };
        this.fbPost({ type: 'expandResult', parentUrl: url, ...data });
    }

    private async fbScanDir(url: string, storageOptions: string | undefined): Promise<void> {
        const so = storageOptions ? JSON.parse(storageOptions) : null;
        const client = ServerClient.get();

        const [scanResult, infoResult, enumsResult] = await Promise.all([
            fbCall('scan_directory', so ? { url, storage_options: so } : { url }),
            client.info(),
            client.enumMembers(),
        ]);

        const data = (scanResult.data as Record<string, unknown>) || {
            url, error: scanResult.stderr || `exit ${scanResult.code}`,
        };
        this.fbPost({ type: 'projectScanned', info: infoResult || {}, enums: enumsResult || {}, ...data });
    }

    // =========================================================================
    // HTML generation
    // =========================================================================
    private getHtml(initialTab: 'library' | 'filebrowser'): string {
        const webview = this.panel.webview;
        const nonce = getNonce();
        const csp = [
            `default-src 'none'`,
            `style-src ${webview.cspSource} 'unsafe-inline'`,
            `img-src ${webview.cspSource} data:`,
            `script-src 'nonce-${nonce}'`,
        ].join('; ');

        // Read shared panel assets (for the library tab and the fb scan pane)
        const webuiDir = path.resolve(__dirname, '..', '..', 'src', 'projspec', 'webui');
        let panelCss = '', panelJs = '', panelBodyHtml = '';
        try {
            panelJs  = fs.readFileSync(path.join(webuiDir, 'panel.js'),  'utf-8');
            panelCss = fs.readFileSync(path.join(webuiDir, 'panel.css'), 'utf-8');
            const rawHtml = fs.readFileSync(path.join(webuiDir, 'panel.html'), 'utf-8');
            const icons = JSON.parse(fs.readFileSync(path.join(webuiDir, 'chrome.json'), 'utf-8'));
            let html = rawHtml;
            for (const [key, glyph] of Object.entries(icons) as [string, string][]) {
                html = html.split(`<!--ICON:${key}-->`).join(glyph);
            }
            html = html.replace('/*__CSS__*/', panelCss);
            html = html.replace('<script>/*__JS__*/</script>', '');
            html = html.replace('<!--BOOTSTRAP-->', '');
            const bodyStart = html.indexOf('<body>') + '<body>'.length;
            const bodyEnd   = html.lastIndexOf('</body>');
            panelBodyHtml = html.slice(bodyStart, bodyEnd).trim();
        } catch (e) {
            log(`panel asset read error: ${e}`);
        }

        const fbCss = getSharedFbCss();
        const fbJs  = getSharedFbJs();

        // -----------------------------------------------------------------
        // Bootstrap scripts
        // -----------------------------------------------------------------

        // (1) Library tab panel bootstrap:
        //     - Captures acquireVsCodeApi() into window.__combinedVscode
        //     - Sets projspecRoot to #tab-library
        //     - Installs a transport that tags all sends with {tab:'library'}
        //     - The panel.js onReady callback stores dispatch as __libDispatch
        const libBootstrap = `(function(){
var api = acquireVsCodeApi();
window.__combinedVscode = api;
window.projspecRoot = document.getElementById('tab-library');
window.projspecTransport = {
  send: function(msg) { api.postMessage(Object.assign({}, msg, {tab:'library'})); },
  onReady: function(d) {
    window.__libDispatch = d;
    if (window.__libPending) { window.__libPending.forEach(function(m){d(m);}); delete window.__libPending; }
  }
};
})()`;

        // (2) FB scan-pane bootstrap (inside the file browser tab):
        //     - Sets projspecRoot to #fb-scan-panel-root
        //     - Installs a no-send transport (the scan pane is display-only)
        //     - onReady stores dispatch as __fbPanelDispatch, drains pending queue
        const fbScanBootstrap = `(function(){
var root = document.getElementById('fb-scan-panel-root');
if (!root) return;
var pending = [];
window.__fbPanelDeliver = function(msg) {
  if (window.__fbPanelDispatch) { window.__fbPanelDispatch(msg); }
  else { pending.push(msg); }
};
window.projspecRoot = root;
window.projspecTransport = {
  send: function(msg) {
    if (window.__combinedVscode) {
      window.__combinedVscode.postMessage(Object.assign({}, msg, {tab:'library'}));
    }
  },
  onReady: function(d) {
    window.__fbPanelDispatch = d;
    pending.forEach(function(m){d(m);}); pending = [];
    delete window.projspecRoot; delete window.projspecTransport;
  }
};
})()`;

        // (3) File browser bootstrap:
        //     - Sets window.projspecFbTransport so filebrowser.js uses the
        //       VS Code message API rather than falling back to the no-op stub.
        //     - send() tags every outbound message with {tab:'fb'} so
        //       onMessage() routes it to onFbMessage().
        //     - onReady() stores the filebrowser dispatch function and drains
        //       any messages that arrived before the panel finished init.
        //     - The host delivers inbound messages by calling
        //       window.__projspecFbDeliver(msg), which is wired up here.
        const fbBootstrap = `(function(){
var dispatch = null;
var inbox = [];
window.__projspecFbDeliver = function(msg) {
    if (dispatch) { dispatch(msg); }
    else { inbox.push(msg); }
};
window.projspecFbTransport = {
    send: function(msg) {
        window.__combinedVscode.postMessage(Object.assign({}, msg, {tab:'fb'}));
    },
    onReady: function(d) {
        dispatch = d;
        while (inbox.length) { dispatch(inbox.shift()); }
    },
};
window.projspecFbRoot = document.getElementById('tab-filebrowser') || document;
})()`;

        // filebrowser.js uses window.projspecFbTransport exclusively (no
        // acquireVsCodeApi() call, no window.addEventListener).  No patching needed.
        const fbJsWrapped = fbJs;

        // (4) Combined coordination script:
        //     - Tab-switching logic
        //     - Routes incoming host messages by 'tab' field
        const combinedJs = getCombinedJs(initialTab);

        const libTabClass = initialTab === 'library' ? 'tab-pane active' : 'tab-pane hidden';
        const fbTabClass  = initialTab === 'filebrowser' ? 'tab-pane active' : 'tab-pane hidden';
        const libBtnClass = initialTab === 'library' ? 'tab-btn active' : 'tab-btn';
        const fbBtnClass  = initialTab === 'filebrowser' ? 'tab-btn active' : 'tab-btn';

        const fbBodyHtml = getFbHtmlBody(panelBodyHtml);

        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<style>
${getSharedTabsCss() || getCombinedCss()}
${panelCss}
${fbCss}
</style>
<title>projspec</title>
</head>
<body>
<div id="tab-bar">
  <button class="${libBtnClass}" data-tab="library" id="tab-btn-library">Project Library</button>
  <button class="${fbBtnClass}" data-tab="filebrowser" id="tab-btn-filebrowser">&#128193; File Browser</button>
</div>
<div id="tab-library" class="${libTabClass}">
${panelBodyHtml}
</div>
<div id="tab-filebrowser" class="${fbTabClass}">
${fbBodyHtml}
</div>
<script nonce="${nonce}">${libBootstrap}</script>
<script nonce="${nonce}">${panelJs}</script>
<script nonce="${nonce}">${fbScanBootstrap}</script>
<script nonce="${nonce}">${panelJs}</script>
<script nonce="${nonce}">${combinedJs}</script>
<script nonce="${nonce}">${fbBootstrap}</script>
<script nonce="${nonce}">${fbJsWrapped}</script>
</body>
</html>`;
    }

    // =========================================================================
    // Dispose
    // =========================================================================
    private dispose(): void {
        CombinedPanel.current = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) { d.dispose(); }
        }
    }
}

// ---------------------------------------------------------------------------
// Tab CSS
// ---------------------------------------------------------------------------
function getCombinedCss(): string {
    return `
/* Reset height so the tab-based layout fills the viewport */
html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; }

/* Tab bar */
#tab-bar {
    display: flex;
    gap: 0;
    border-bottom: 2px solid var(--vscode-panel-border);
    background: var(--vscode-editorGroupHeader-tabsBackground, var(--vscode-editor-background));
    flex-shrink: 0;
}
.tab-btn {
    background: transparent;
    color: var(--vscode-foreground);
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    padding: 7px 18px;
    font-size: 13px;
    cursor: pointer;
    font-family: var(--vscode-font-family);
    outline: none;
    white-space: nowrap;
}
.tab-btn:hover { background: var(--vscode-list-hoverBackground); }
.tab-btn.active {
    border-bottom-color: var(--vscode-focusBorder, var(--vscode-button-background));
    color: var(--vscode-foreground);
    font-weight: 600;
}

/* Panes */
.tab-pane {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 36px);
    overflow: hidden;
}
.tab-pane.hidden { display: none !important; }

/* Override panel #app height inside the library tab */
#tab-library #app { height: 100%; overflow: hidden; }

/* Override fb-app height inside the filebrowser tab */
#tab-filebrowser #fb-app { height: 100%; }
`;
}

// ---------------------------------------------------------------------------
// Combined coordination JS (webview side)
// ---------------------------------------------------------------------------
function getCombinedJs(initialTab: 'library' | 'filebrowser'): string {
    const initTabStr = JSON.stringify(initialTab);
    return `
(function() {
    // ── tab switching ─────────────────────────────────────────────────────
    var activeTab = ${initTabStr};

    function showTab(tab) {
        activeTab = tab;
        var tabs = ['library', 'filebrowser'];
        tabs.forEach(function(t) {
            var pane = document.getElementById('tab-' + t);
            var btn  = document.getElementById('tab-btn-' + t);
            if (!pane || !btn) return;
            if (t === tab) {
                pane.classList.remove('hidden');
                pane.classList.add('active');
                btn.classList.add('active');
            } else {
                pane.classList.add('hidden');
                pane.classList.remove('active');
                btn.classList.remove('active');
            }
        });
    }

    document.getElementById('tab-btn-library').addEventListener('click', function() {
        showTab('library');
    });
    document.getElementById('tab-btn-filebrowser').addEventListener('click', function() {
        showTab('filebrowser');
    });

    // ── message routing ────────────────────────────────────────────────────
    // The host sends messages with a 'tab' field: 'library' or 'filebrowser'.
    // We route them to the appropriate dispatch function.
    window.addEventListener('message', function(ev) {
        var msg = ev.data;
        if (!msg || !msg.type) return;

        if (msg.type === 'switchTab') {
            showTab(msg.tab);
            return;
        }

        if (msg.tab === 'library') {
            // Deliver to the library panel
            if (msg.type === 'loading') {
                var spinner = document.querySelector('#tab-library #spinner');
                if (spinner) spinner.classList.toggle('hidden', !msg.loading);
                return;
            }
            if (msg.type === 'data') {
                if (window.__libDispatch) {
                    window.__libDispatch(msg);
                } else {
                    if (!window.__libPending) window.__libPending = [];
                    window.__libPending.push(msg);
                }
                // If selectUrl is specified, select that project after rendering
                if (msg.selectUrl) {
                    setTimeout(function() {
                        var el = document.querySelector('#tab-library .project[data-url="' + msg.selectUrl.replace(/"/g, '\\"') + '"]');
                        if (el) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                            el.classList.add('active');
                        }
                    }, 100);
                }
                return;
            }
            if (msg.type === 'openCreateSpecModal') {
                if (window.__libDispatch) window.__libDispatch(msg);
                return;
            }
            // fallthrough: deliver all to libDispatch
            if (window.__libDispatch) window.__libDispatch(msg);
            return;
        }

        if (msg.tab === 'filebrowser') {
            // Deliver to the filebrowser panel via its transport dispatch
            if (typeof window.__projspecFbDeliver === 'function') {
                window.__projspecFbDeliver(msg);
            }
            return;
        }
    });
})();
`;
}

// ---------------------------------------------------------------------------
// File browser HTML body (same as FB_HTML_BODY, with the scan panel injected)
// ---------------------------------------------------------------------------
function getFbHtmlBody(panelBodyHtml: string): string {
    const fbHtmlBody = `
<div id="fb-app">
  <div id="fb-tree-pane">
    <div id="fb-toolbar">
      <button id="btn-back"    class="fb-icon-btn" title="Back">&#9668;</button>
      <button id="btn-up"      class="fb-icon-btn" title="Up one level">&#8679;</button>
      <button id="btn-refresh" class="fb-icon-btn" title="Refresh">&#8635;</button>
      <button id="btn-bm-dropdown" class="fb-icon-btn" title="Bookmarks">&#9733;</button>
      <button id="btn-so"      class="fb-icon-btn" title="Storage options">&#128273;</button>
      <label id="fb-show-hidden-label" class="fb-checkbox-label" title="Show hidden files and directories">
        <input type="checkbox" id="fb-show-hidden" /> Show hidden
      </label>
      <div class="fb-spacer"></div>
      <button id="btn-new-file" class="fb-icon-btn" title="New file">+F</button>
      <button id="btn-new-dir"  class="fb-icon-btn" title="New folder">+D</button>
    </div>
    <div id="fb-url-bar">
      <input id="fb-url-input" type="text" spellcheck="false" autocomplete="off" placeholder="Enter URL or path" />
      <button id="btn-go" class="fb-go-btn">Go</button>
    </div>
    <div id="fb-breadcrumb"></div>
    <div id="fb-file-list">
      <div id="fb-col-headers">
        <span class="fb-col-name fb-col-hdr" data-col="name">Name <span class="fb-sort-arrow"></span></span>
        <span class="fb-col-size fb-col-hdr" data-col="size">Size <span class="fb-sort-arrow"></span></span>
        <span class="fb-col-mtime fb-col-hdr" data-col="mtime">Modified <span class="fb-sort-arrow"></span></span>
      </div>
      <div id="fb-empty"   class="fb-status hidden">Directory is empty.</div>
      <div id="fb-error"   class="fb-status fb-error hidden"></div>
      <div id="fb-entries"></div>
    </div>
    <div id="fb-spinner" class="fb-spinner hidden">
      <span class="spin">&#9203;</span> Loading...
    </div>
  </div>
  <div id="fb-info-pane">
    <div id="fb-info-header">
      <div id="fb-info-title">No file selected</div>
      <div id="fb-info-actions" class="hidden">
        <button id="btn-add-to-lib"  title="Add to projspec library">+ Library</button>
      </div>
    </div>
    <div id="fb-info-top">
      <div id="fb-info-meta"></div>
      <div id="fb-info-preview"></div>
    </div>
    <div id="fb-scan-pane" class="hidden">
      <div id="fb-scan-panel-root">${panelBodyHtml}</div>
      <div id="fb-file-content" class="hidden"></div>
    </div>
  </div>
</div>
<div id="bm-panel" class="hidden">
  <div class="bm-header">Bookmarks <button id="bm-close" class="fb-icon-btn">X</button></div>
  <div id="bm-list"></div>
  <div class="bm-footer">
    <button id="btn-bm-add-current">+ Bookmark current location</button>
  </div>
</div>
<div id="so-overlay" class="overlay hidden">
  <div class="fb-modal" role="dialog">
    <div class="fb-modal-title">Storage Options</div>
    <div class="fb-modal-body">
      <p class="hint">JSON dictionary of fsspec storage options (credentials, endpoints, etc.).</p>
      <label for="so-input">Storage options (JSON):</label>
      <textarea id="so-input" rows="5" spellcheck="false" placeholder='{"key": "...", "secret": "..."}'></textarea>
    </div>
    <div class="fb-modal-footer">
      <button id="so-cancel" class="secondary">Cancel</button>
      <button id="so-ok" class="primary">Apply</button>
    </div>
  </div>
</div>
<div id="newentry-overlay" class="overlay hidden">
  <div class="fb-modal" role="dialog">
    <div class="fb-modal-title" id="newentry-title">New file</div>
    <div class="fb-modal-body">
      <label for="newentry-name">Name:</label>
      <input type="text" id="newentry-name" autocomplete="off" spellcheck="false" />
    </div>
    <div class="fb-modal-footer">
      <button id="newentry-cancel" class="secondary">Cancel</button>
      <button id="newentry-ok" class="primary">Create</button>
    </div>
  </div>
</div>
<div id="rename-overlay" class="overlay hidden">
  <div class="fb-modal" role="dialog">
    <div class="fb-modal-title">Rename</div>
    <div class="fb-modal-body">
      <label for="rename-input">New name:</label>
      <input type="text" id="rename-input" autocomplete="off" spellcheck="false" />
    </div>
    <div class="fb-modal-footer">
      <button id="rename-cancel" class="secondary">Cancel</button>
      <button id="rename-ok" class="primary">Rename</button>
    </div>
  </div>
</div>
<div id="fb-ctxmenu" class="hidden">
  <div class="fb-ctxmenu-item" data-action="open">Open</div>
  <div class="fb-ctxmenu-sep"></div>
  <div class="fb-ctxmenu-item" data-action="copy">Copy</div>
  <div class="fb-ctxmenu-item" data-action="cut">Cut</div>
  <div class="fb-ctxmenu-item" data-action="paste">Paste</div>
  <div class="fb-ctxmenu-sep"></div>
  <div class="fb-ctxmenu-item" data-action="rename">Rename</div>
  <div class="fb-ctxmenu-item fb-ctxmenu-danger" data-action="delete">Delete</div>
</div>
<div id="paste-confirm-overlay" class="overlay hidden">
  <div class="fb-modal" role="dialog">
    <div class="fb-modal-title">Confirm large copy</div>
    <div class="fb-modal-body">
      <p id="paste-confirm-msg" class="hint"></p>
    </div>
    <div class="fb-modal-footer">
      <button id="paste-confirm-cancel" class="secondary">Cancel</button>
      <button id="paste-confirm-ok" class="primary">Copy anyway</button>
    </div>
  </div>
</div>
`;
    return fbHtmlBody;
}
