/**
 * serverClient.ts
 * ===============
 * Manages a single `projspec serve` background process and provides typed
 * wrappers for every server endpoint.
 *
 * Lifecycle
 * ---------
 * Call `ServerClient.get()` to obtain (or lazily create) the singleton.  It
 * generates a random bearer token, then starts `projspec serve --port-file
 * <tmp> --token <token>` in the background.  The port file contains
 * "scheme:port:token" and is read once the server has written it.  All
 * requests carry an `Authorization: Bearer <token>` header.
 *
 * SSL
 * ---
 * Pass `--ssl-certfile` / `--ssl-keyfile` to the server to enable HTTPS; the
 * scheme in the port file switches to "https" and the client uses Node's
 * built-in `https` module automatically.
 *
 * Fallback
 * --------
 * If the server fails to start within the timeout (fastapi/uvicorn not
 * installed, or projspec too old), every method transparently falls back to
 * the original subprocess approach so the extension keeps working.
 */

import * as childProcess from 'child_process';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as http from 'http';
import * as https from 'https';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';
import { parseJsonOutput, RunResult } from './projspec';

// ---------------------------------------------------------------------------
// Logging — mirrors combinedPanel.ts: appends to vscode.log in config dir.
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

// ---------------------------------------------------------------------------
// Python executable helper
// ---------------------------------------------------------------------------
function python3(): string {
    return process.env['PROJSPEC_PYTHON'] || 'python3';
}

// ---------------------------------------------------------------------------
// Token generation — 32 random hex bytes (256 bits)
// ---------------------------------------------------------------------------
function generateToken(): string {
    return crypto.randomBytes(32).toString('hex');
}

// ---------------------------------------------------------------------------
// HTTP/HTTPS helpers
// ---------------------------------------------------------------------------

/** Convert a DER buffer to a PEM string (certificate). */
function derToPem(der: Buffer): string {
    const b64 = der.toString('base64');
    const lines = b64.match(/.{1,64}/g)!.join('\n');
    return `-----BEGIN CERTIFICATE-----\n${lines}\n-----END CERTIFICATE-----\n`;
}

function httpRequest(
    scheme: 'http' | 'https',
    options: http.RequestOptions,
    token: string,
    agent: https.Agent | undefined,
    body?: string,
): Promise<{ statusCode: number; data: unknown }> {
    const headers: Record<string, string | number> = {
        ...(options.headers as Record<string, string | number> | undefined ?? {}),
    };
    if (token) { headers['Authorization'] = `Bearer ${token}`; }
    const finalOptions: http.RequestOptions = { ...options, headers };
    if (agent) { (finalOptions as https.RequestOptions).agent = agent; }

    return new Promise((resolve, reject) => {
        const transport = scheme === 'https' ? https : http;
        const req = (transport as typeof http).request(finalOptions, (res) => {
            let raw = '';
            res.on('data', (chunk: Buffer) => { raw += chunk.toString(); });
            res.on('end', () => {
                try {
                    resolve({ statusCode: res.statusCode ?? 0, data: JSON.parse(raw) });
                } catch (e) {
                    reject(new Error(`JSON parse error: ${e} — raw: ${raw.slice(0, 200)}`));
                }
            });
        });
        req.on('error', reject);
        if (body !== undefined) { req.write(body); }
        req.end();
    });
}

async function get(
    scheme: 'http' | 'https',
    port: number,
    urlPath: string,
    token: string,
    agent?: https.Agent,
): Promise<unknown> {
    const r = await httpRequest(scheme, { hostname: '127.0.0.1', port, path: urlPath, method: 'GET' }, token, agent);
    return r.data;
}

async function post(
    scheme: 'http' | 'https',
    port: number,
    urlPath: string,
    body: unknown,
    token: string,
    agent?: https.Agent,
): Promise<unknown> {
    const bodyStr = JSON.stringify(body);
    const r = await httpRequest(
        scheme,
        {
            hostname: '127.0.0.1',
            port,
            path: urlPath,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(bodyStr),
            },
        },
        token,
        agent,
        bodyStr,
    );
    return r.data;
}

// ---------------------------------------------------------------------------
// ServerClient
// ---------------------------------------------------------------------------
/** How long to wait for the server to write its port file (ms). */
const START_TIMEOUT_MS = 15_000;
/** How often to poll for the port file (ms). */
const POLL_INTERVAL_MS = 100;

export class ServerClient {
    private static _instance: ServerClient | undefined;

    private _port: number | null = null;
    private _scheme: 'http' | 'https' = 'https';
    private _token: string;
    private _agent: https.Agent | undefined;
    private _ready: Promise<number | null>;
    private _proc: childProcess.ChildProcess | null = null;
    private _portFile: string;
    private _disposed = false;
    private _startFailed = false;

    // -------------------------------------------------------------------------
    // Singleton
    // -------------------------------------------------------------------------
    static get(): ServerClient {
        if (!ServerClient._instance) {
            ServerClient._instance = new ServerClient();
        }
        return ServerClient._instance;
    }

    static dispose(): void {
        ServerClient._instance?.dispose();
        ServerClient._instance = undefined;
    }

    // -------------------------------------------------------------------------
    // Constructor — generates token and starts the server immediately
    // -------------------------------------------------------------------------
    private constructor() {
        this._token = generateToken();
        this._portFile = path.join(os.tmpdir(), `projspec-server-${process.pid}.port`);
        this._ready = this._start();
    }

    private async _start(): Promise<number | null> {
        // Clean up any stale port file from a previous run
        try { fs.unlinkSync(this._portFile); } catch { /* ok */ }

        log(`Starting projspec server, port-file=${this._portFile}`);
        const serverArgs = ['--port', '0', '--port-file', this._portFile, '--token', this._token];
        const pyArgs = ['-m', 'projspec', 'serve', ...serverArgs];

        try {
            // Prefer the dedicated `projspec-server` console script; fall back
            // to `python3 -m projspec serve` for environments where only the
            // package (not the scripts) is on PATH.
            this._proc = childProcess.spawn(
                'projspec-server',
                serverArgs,
                {
                    env: process.env,
                    stdio: ['ignore', 'pipe', 'pipe'],
                    detached: false,
                },
            );

            this._proc.stdout?.on('data', (d: Buffer) => log(`[server stdout] ${d.toString().trimEnd()}`));
            this._proc.stderr?.on('data', (d: Buffer) => log(`[server stderr] ${d.toString().trimEnd()}`));
            this._proc.on('exit', (code) => {
                log(`Server process exited with code ${code}`);
                this._port = null;
                // A successfully-spawned process that exits before writing the
                // port file (e.g. bad CLI args, missing runtime deps) will
                // never come back — fail fast instead of polling for the
                // full timeout.
                this._startFailed = true;
            });
            // If projspec-server is not on PATH, retry with python3 -m projspec serve
            this._proc.on('error', (err: NodeJS.ErrnoException) => {
                if (err.code === 'ENOENT') {
                    log('projspec-server not found on PATH, retrying with python3 -m projspec serve');
                    const retryProc = childProcess.spawn(
                        python3(), pyArgs,
                        { env: process.env, stdio: ['ignore', 'pipe', 'pipe'], detached: false },
                    );
                    retryProc.stdout?.on('data', (d: Buffer) => log(`[server stdout] ${d.toString().trimEnd()}`));
                    retryProc.stderr?.on('data', (d: Buffer) => log(`[server stderr] ${d.toString().trimEnd()}`));
                    retryProc.on('exit', (code) => {
                        log(`Server process exited with code ${code}`);
                        this._port = null;
                        this._startFailed = true;
                    });
                    retryProc.on('error', (e) => {
                        log(`Server process error: ${e}`);
                        this._port = null;
                        this._startFailed = true;
                    });
                    this._proc = retryProc;
                } else {
                    log(`Server process error: ${err}`);
                    this._port = null;
                    this._startFailed = true;
                }
            });

            // Wait for the port file — format: "https:port:token:certHex"
            const deadline = Date.now() + START_TIMEOUT_MS;
            while (Date.now() < deadline) {
                if (this._disposed) { return null; }
                if (this._startFailed) {
                    log('Server process exited before becoming ready — falling back to subprocess mode');
                    this._killProc();
                    return null;
                }
                try {
                    const raw = fs.readFileSync(this._portFile, 'utf-8').trim();
                    // Split on ':' but only for the first 3 colons;
                    // certHex contains no colons so parts[3] is always the full hex.
                    const firstColon  = raw.indexOf(':');
                    const secondColon = raw.indexOf(':', firstColon + 1);
                    const thirdColon  = raw.indexOf(':', secondColon + 1);
                    if (firstColon > 0 && secondColon > firstColon && thirdColon > secondColon) {
                        const scheme   = raw.slice(0, firstColon) as 'http' | 'https';
                        const port     = parseInt(raw.slice(firstColon + 1, secondColon), 10);
                        const token    = raw.slice(secondColon + 1, thirdColon);
                        const certHex  = raw.slice(thirdColon + 1);
                        if (port > 0) {
                            this._scheme = scheme;
                            // Build a pinned HTTPS agent from the server's self-signed cert
                            if (scheme === 'https' && certHex) {
                                const certDer = Buffer.from(certHex, 'hex');
                                const certPem = derToPem(certDer);
                                this._agent = new https.Agent({ ca: certPem });
                            }
                            // /ping requires no token — use the agent but empty token
                            await get(scheme, port, '/ping', '', this._agent);
                            log(`Server ready on ${scheme}://127.0.0.1:${port}`);
                            this._port = port;
                            return port;
                        }
                    }
                } catch { /* not ready yet */ }
                await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
            }
            log('Server start timed out — falling back to subprocess mode');
            this._killProc();
            return null;
        } catch (err) {
            log(`Failed to start server: ${err}`);
            return null;
        }
    }

    private _killProc(): void {
        if (this._proc && !this._proc.killed) {
            try { this._proc.kill(); } catch { /* ok */ }
            this._proc = null;
        }
        try { fs.unlinkSync(this._portFile); } catch { /* ok */ }
    }

    dispose(): void {
        this._disposed = true;
        this._killProc();
    }

    // -------------------------------------------------------------------------
    // Core request helper — resolves the port then sends the request.
    // Returns null if the server is unavailable (caller should fall back).
    // -------------------------------------------------------------------------
    private async _get(endpoint: string): Promise<unknown | null> {
        const port = await this._ready;
        if (port === null) { return null; }
        try { return await get(this._scheme, port, endpoint, this._token, this._agent); }
        catch (e) { log(`GET ${endpoint} failed: ${e}`); return null; }
    }

    private async _post(endpoint: string, body: unknown): Promise<unknown | null> {
        const port = await this._ready;
        if (port === null) { return null; }
        try { return await post(this._scheme, port, endpoint, body, this._token, this._agent); }
        catch (e) { log(`POST ${endpoint} failed: ${e}`); return null; }
    }

    // =========================================================================
    // Public API — one method per server endpoint.
    // Each method returns the parsed JSON response, or null on failure.
    // =========================================================================

    async ping(): Promise<boolean> {
        const r = await this._get('/ping');
        return r !== null;
    }

    async info(): Promise<unknown | null> {
        return this._get('/info');
    }

    async enumMembers(): Promise<unknown | null> {
        return this._get('/enum_members');
    }

    async libraryList(): Promise<unknown | null> {
        return this._get('/library');
    }

    async libraryDelete(url: string): Promise<unknown | null> {
        return this._post('/library/delete', { url });
    }

    async scan(
        scanPath: string,
        addToLibrary: boolean,
        storageOptions?: string,
    ): Promise<unknown | null> {
        return this._post('/scan', {
            path: scanPath,
            add_to_library: addToLibrary,
            storage_options: storageOptions || null,
        });
    }

    async create(spec: string, scanPath: string): Promise<unknown | null> {
        return this._post('/create', { spec, path: scanPath });
    }

    // --- Filebrowser ---

    async browse(url: string, storageOptions?: Record<string, unknown> | null): Promise<unknown | null> {
        return this._post('/filebrowser/browse', { url, storage_options: storageOptions ?? null });
    }

    async inspect(url: string, storageOptions?: Record<string, unknown> | null): Promise<unknown | null> {
        return this._post('/filebrowser/inspect', { url, storage_options: storageOptions ?? null });
    }

    async inspectAsProject(url: string, storageOptions?: Record<string, unknown> | null): Promise<unknown | null> {
        return this._post('/filebrowser/inspect_as_project', { url, storage_options: storageOptions ?? null });
    }

    async scanDirectory(url: string, storageOptions?: Record<string, unknown> | null): Promise<unknown | null> {
        return this._post('/filebrowser/scan_directory', { url, storage_options: storageOptions ?? null });
    }

    async readFile(
        url: string,
        storageOptions?: Record<string, unknown> | null,
        maxBytes?: number,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/read_file', {
            url,
            storage_options: storageOptions ?? null,
            max_bytes: maxBytes ?? null,
        });
    }

    async writeFile(
        url: string,
        content: string,
        storageOptions?: Record<string, unknown> | null,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/write_file', {
            url,
            content,
            storage_options: storageOptions ?? null,
        });
    }

    async deleteEntry(
        url: string,
        recursive: boolean,
        storageOptions?: Record<string, unknown> | null,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/delete', {
            url,
            recursive,
            storage_options: storageOptions ?? null,
        });
    }

    async move(
        src: string,
        dst: string,
        storageOptions?: Record<string, unknown> | null,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/move', {
            src,
            dst,
            storage_options: storageOptions ?? null,
        });
    }

    async mkdir(url: string, storageOptions?: Record<string, unknown> | null): Promise<unknown | null> {
        return this._post('/filebrowser/mkdir', { url, storage_options: storageOptions ?? null });
    }

    async addToLibrary(
        url: string,
        storageOptions?: Record<string, unknown> | null,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/add_to_library', {
            url,
            storage_options: storageOptions ?? null,
        });
    }

    async protocols(): Promise<unknown | null> {
        return this._get('/filebrowser/protocols');
    }

    async bookmarksList(): Promise<unknown | null> {
        return this._get('/filebrowser/bookmarks');
    }

    async bookmarkAdd(
        url: string,
        label?: string,
        storageOptions?: Record<string, unknown> | null,
    ): Promise<unknown | null> {
        return this._post('/filebrowser/bookmarks/add', {
            url,
            label: label ?? '',
            storage_options: storageOptions ?? null,
        });
    }

    async bookmarkRemove(url: string): Promise<unknown | null> {
        return this._post('/filebrowser/bookmarks/remove', { url });
    }
}

// ---------------------------------------------------------------------------
// Fallback subprocess helpers (unchanged from previous implementation)
// These are used when the server is unavailable.
// ---------------------------------------------------------------------------

/**
 * Run a projspec.filebrowser function via python3 subprocess (fallback).
 * Identical to the implementation in combinedPanel.ts / fileBrowserPanel.ts.
 */
export function runFbPythonFallback(
    fn: string,
    kwargs: Record<string, unknown>,
): Promise<{ data: unknown; stderr: string; code: number | null }> {
    const fbPath = path.resolve(__dirname, '..', '..', 'src', 'projspec', 'filebrowser.py');
    const script = [
        'import sys, json, importlib.util',
        `spec = importlib.util.spec_from_file_location("projspec_filebrowser", ${JSON.stringify(fbPath)})`,
        'mod = importlib.util.module_from_spec(spec)',
        'spec.loader.exec_module(mod)',
        'kwargs = json.loads(sys.argv[1])',
        `result = getattr(mod, ${JSON.stringify(fn)})(**kwargs)`,
        'print(json.dumps(result))',
    ].join('\n');
    const kwargsStr = JSON.stringify(kwargs);
    log(`[fallback] runFbPython ${fn}`);
    return new Promise((resolve) => {
        const proc = childProcess.spawn(python3(), ['-c', script, kwargsStr], { env: process.env });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (d: Buffer) => { stdout += d.toString(); });
        proc.stderr.on('data', (d: Buffer) => { stderr += d.toString(); });
        proc.on('error', (err: Error) => resolve({ data: null, stderr: String(err), code: -1 }));
        proc.on('close', (code: number | null) => {
            let data: unknown = null;
            try { data = parseJsonOutput(stdout); } catch { /* ok */ }
            resolve({ data, stderr, code });
        });
    });
}

/**
 * Run `projspec <args>` subprocess (fallback).
 */
export function runProjspecFallback(args: string[]): Promise<RunResult> {
    return new Promise((resolve) => {
        const proc = childProcess.spawn('projspec', args, { env: process.env });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (d: Buffer) => { stdout += d.toString(); });
        proc.stderr.on('data', (d: Buffer) => { stderr += d.toString(); });
        proc.on('error', (err) => resolve({ stdout, stderr: stderr + '\n' + String(err), code: -1 }));
        proc.on('close', (code) => resolve({ stdout, stderr, code }));
    });
}

// ---------------------------------------------------------------------------
// Convenience wrappers used by combinedPanel.ts
// These call the server and fall back to subprocess automatically.
// ---------------------------------------------------------------------------

type FbResult = { data: unknown; stderr: string; code: number | null };

/**
 * Call a filebrowser function: server first, subprocess fallback.
 * Returns a RunResult-shaped object so existing call sites need minimal changes.
 */
export async function fbCall(
    fn: string,
    kwargs: Record<string, unknown>,
): Promise<FbResult> {
    const client = ServerClient.get();
    // Map fn name to the appropriate server method
    const so = (kwargs['storage_options'] as Record<string, unknown> | null | undefined) ?? null;
    let result: unknown | null = null;
    try {
        switch (fn) {
            case 'bookmarks_list':      result = await client.bookmarksList(); break;
            case 'supported_protocols': result = await client.protocols(); break;
            case 'browse':              result = await client.browse(kwargs['url'] as string, so); break;
            case 'inspect_as_project':  result = await client.inspectAsProject(kwargs['url'] as string, so); break;
            case 'scan_directory':      result = await client.scanDirectory(kwargs['url'] as string, so); break;
            case 'read_file':
                result = await client.readFile(
                    kwargs['url'] as string,
                    so,
                    kwargs['max_bytes'] as number | undefined,
                );
                break;
            case 'write_file':
                result = await client.writeFile(kwargs['url'] as string, kwargs['content'] as string, so);
                break;
            case 'delete':
                result = await client.deleteEntry(
                    kwargs['url'] as string,
                    (kwargs['recursive'] as boolean | undefined) ?? false,
                    so,
                );
                break;
            case 'move':
                result = await client.move(kwargs['src'] as string, kwargs['dst'] as string, so);
                break;
            case 'mkdir':               result = await client.mkdir(kwargs['url'] as string, so); break;
            case 'add_to_projspec_library': result = await client.addToLibrary(kwargs['url'] as string, so); break;
            case 'bookmark_add':
                result = await client.bookmarkAdd(
                    kwargs['url'] as string,
                    kwargs['label'] as string | undefined,
                    so,
                );
                break;
            case 'bookmark_remove':     result = await client.bookmarkRemove(kwargs['url'] as string); break;
            default:
                log(`Unknown fn '${fn}', falling back to subprocess`);
        }
    } catch (e) {
        log(`Server call for '${fn}' threw: ${e}`);
    }

    if (result !== null) {
        return { data: result, stderr: '', code: 0 };
    }
    // Fall back to subprocess
    return runFbPythonFallback(fn, kwargs);
}
