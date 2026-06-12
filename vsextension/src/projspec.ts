import * as childProcess from 'child_process';
import * as vscode from 'vscode';

export interface RunResult {
    stdout: string;
    stderr: string;
    code: number | null;
}

/**
 * Run `projspec <args...>` and collect the full stdout/stderr.
 *
 * We never pass user input as a shell string - args are passed as argv so
 * there is no shell interpretation.
 */
export function runProjspec(args: string[], opts: { cwd?: string } = {}): Promise<RunResult> {
    return new Promise((resolve) => {
        const proc = childProcess.spawn('projspec', args, {
            cwd: opts.cwd,
            env: process.env,
        });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (d) => { stdout += d.toString(); });
        proc.stderr.on('data', (d) => { stderr += d.toString(); });
        proc.on('error', (err) => {
            resolve({ stdout, stderr: stderr + '\n' + String(err), code: -1 });
        });
        proc.on('close', (code) => {
            resolve({ stdout, stderr, code });
        });
    });
}

/**
 * Parse the JSON emitted by a `projspec ... --json-out` command.  Some
 * commands print a banner/warnings before the JSON, so we extract the first
 * balanced JSON object from the output.
 */
export function parseJsonOutput(stdout: string): unknown {
    const trimmed = stdout.trim();
    // Fast path: whole output is JSON
    try {
        return JSON.parse(trimmed);
    } catch {
        // fall through
    }
    // Slow path: find first '{' or '[' and try each candidate from there
    const start = trimmed.search(/[{[]/);
    if (start < 0) {
        throw new Error('No JSON object found in output');
    }
    const candidate = trimmed.slice(start);
    return JSON.parse(candidate);
}

/** Run the `projspec info` command and return the parsed JSON. */
export async function getInfo(): Promise<InfoData> {
    const res = await runProjspec(['info']);
    if (res.code !== 0) {
        throw new Error(`projspec info failed: ${res.stderr}`);
    }
    return parseJsonOutput(res.stdout) as InfoData;
}

/**
 * Return a mapping of snake-cased enum class name -> {MEMBER_NAME: value}.
 *
 * ``projspec info`` does not expose enum members, so we invoke python in a
 * subprocess and introspect ``projspec.utils.Enum``'s subclasses.  This keeps
 * the extension from having to embed a static copy of the enum definitions
 * while still letting us render human-readable labels instead of raw ints.
 */
export async function getEnumMembers(): Promise<EnumMembers> {
    const script = [
        'import json, importlib, pkgutil',
        'import projspec.utils as pu',
        'import projspec.content, projspec.artifact',
        'for pkg in (projspec.content, projspec.artifact):',
        "    for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + '.'):",
        '        importlib.import_module(m.name)',
        'from projspec.utils import camel_to_snake',
        'out, seen = {}, set()',
        'def walk(cls):',
        '    for sub in cls.__subclasses__():',
        '        if sub in seen: continue',
        '        seen.add(sub); walk(sub)',
        '        out[camel_to_snake(sub.__name__)] = {m.name: m.value for m in sub}',
        'walk(pu.Enum)',
        'print(json.dumps(out))',
    ].join('\n');
    return new Promise((resolve) => {
        const proc = childProcess.spawn('python3', ['-c', script], { env: process.env });
        let stdout = '';
        proc.stdout.on('data', (d) => { stdout += d.toString(); });
        proc.on('error', () => resolve({}));
        proc.on('close', () => {
            try {
                resolve(JSON.parse(stdout.trim()) as EnumMembers);
            } catch {
                resolve({});
            }
        });
    });
}

/** Run `projspec library list --json-out` and return the parsed JSON. */
export async function getLibrary(): Promise<LibraryData> {
    const res = await runProjspec(['library', 'list', '--json-out']);
    if (res.code !== 0) {
        throw new Error(`projspec library list failed: ${res.stderr}`);
    }
    const parsed = parseJsonOutput(res.stdout);
    if (parsed && typeof parsed === 'object') {
        return parsed as LibraryData;
    }
    return {};
}

/** Scan a path, optionally adding it to the library. */
export async function scan(path: string, addToLibrary: boolean, storageOptions?: string): Promise<RunResult> {
    const args = ['scan'];
    if (addToLibrary) {
        args.push('--library');
    }
    if (storageOptions) {
        args.push('--storage_options', storageOptions);
    }
    args.push(path);
    return runProjspec(args);
}

/** Remove a URL from the library. */
export async function libraryDelete(url: string): Promise<RunResult> {
    return runProjspec(['library', 'delete', url]);
}

/** Create a new spec of type <spec> in path. */
export async function createSpec(spec: string, path: string): Promise<RunResult> {
    return runProjspec(['create', spec, path]);
}

// ---------------------------------------------------------------------------
//  Data shapes emitted by projspec
// ---------------------------------------------------------------------------

export interface InfoEntry {
    doc: string | null;
    link?: string;
    icon?: string;
    create?: boolean;
}

export interface InfoData {
    specs: Record<string, InfoEntry>;
    content: Record<string, InfoEntry>;
    artifact: Record<string, InfoEntry>;
    enum: Record<string, InfoEntry>;
}

export interface ProjectData {
    url: string;
    storage_options?: Record<string, unknown>;
    specs: Record<string, SpecData>;
    contents: Record<string, unknown>;
    artifacts: Record<string, unknown>;
    children?: Record<string, unknown>;
    klass?: [string, string];
    file_count?: string;
    total_size?: string;
    is_writable?: string;
    last_modified?: string;
    last_modified_by?: string;
}

export interface SpecData {
    _contents: Record<string, unknown>;
    _artifacts: Record<string, unknown>;
    klass: [string, string];
}

export type LibraryData = Record<string, ProjectData>;

/** Mapping of enum snake-name -> {MEMBER_NAME: value}. */
export type EnumMembers = Record<string, Record<string, string | number>>;

/**
 * Strip any leading `file://` from a URL so the result can be passed as a
 * path to subprocesses (`code`, `pycharm`, etc.).
 */
export function urlToPath(url: string): string {
    if (url.startsWith('file://')) {
        return url.slice('file://'.length);
    }
    return url;
}

/** Open an OS file browser at the given path. */
export function openInFileBrowser(path: string): void {
    let cmd: string;
    let args: string[];
    switch (process.platform) {
        case 'darwin': cmd = 'open'; args = [path]; break;
        case 'win32':  cmd = 'explorer'; args = [path]; break;
        default:       cmd = 'xdg-open'; args = [path]; break;
    }
    childProcess.spawn(cmd, args, { detached: true, stdio: 'ignore' }).unref();
}

/**
 * Run a command in a new VSCode integrated terminal.  Used for `projspec make`
 * so the user can watch output scroll.
 */
export function runInTerminal(name: string, cmd: string, args: string[]): void {
    const terminal = vscode.window.createTerminal({ name });
    // Shell-quote args that contain whitespace; passing the whole line through
    // sendText is the standard VSCode pattern.
    const quoted = [cmd, ...args].map((a) => /\s/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a).join(' ');
    terminal.show();
    terminal.sendText(quoted, true);
}
