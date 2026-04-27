// projspec VSCode extension — rewritten per ACTIONS.md
import * as vscode from 'vscode';
import { execSync } from 'node:child_process';
import * as path from 'node:path';
import * as os from 'node:os';
import * as fs from 'node:fs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InfoRecord { doc: string | null; link?: string; create?: boolean; }
interface InfoData {
	specs:    Record<string, InfoRecord>;
	content:  Record<string, InfoRecord>;
	artifact: Record<string, InfoRecord>;
	enum:     Record<string, InfoRecord>;
	// Injected after load: maps enum typename -> { value -> member name }
	enumMembers: Record<string, Record<string, string>>;
}

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

let cachedInfo: InfoData | null = null;
let cachedLibraryData: Record<string, any> | null = null;
let detailsPanel: vscode.WebviewPanel | undefined;
let detailsPanelState: { projectUrl: string; selection: string } | undefined;
let extensionLogoUri: vscode.Uri | undefined;
// Reference to the library panel so we can post reload messages to it
let libraryPanel: vscode.WebviewPanel | undefined;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getInfoData(): InfoData | null {
	if (cachedInfo !== null) { return cachedInfo; }
	try {
		const out = execSync('projspec info', { stdio: 'pipe', encoding: 'utf-8' });
		cachedInfo = JSON.parse(out) as InfoData;
	} catch (err) {
		cachedInfo = null;
		showSubprocessError('projspec info', err);
		return null;
	}
	// Resolve enum member names (value -> NAME) via a small Python snippet.
	// This is cheap: it just imports already-loaded projspec classes.
	try {
		const pySnippet = [
			'import json, projspec.utils as u',
			'from projspec.content import environment',  // ensure enums are importable
			'result = {}',
			'for name in ' + JSON.stringify(Object.keys(cachedInfo.enum ?? {})) + ':',
			'    try:',
			'        cls = u.get_cls(name, "enum")',
			'        result[name] = {str(m.value): m.name for m in cls}',
			'    except Exception:',
			'        pass',
			'print(json.dumps(result))',
		].join('\n');
		const membersOut = execSync(`python3 -c "${pySnippet.replace(/"/g, '\\"')}"`, { stdio: 'pipe', encoding: 'utf-8' });
		cachedInfo.enumMembers = JSON.parse(membersOut);
	} catch {
		// Non-fatal: enum values will show as raw integers if this fails
		cachedInfo.enumMembers = {};
	}
	return cachedInfo;
}

function loadLibraryData(): Record<string, any> {
	try {
		const out = execSync('projspec library list --json-out', { stdio: 'pipe', encoding: 'utf-8' });
		cachedLibraryData = JSON.parse(out) as Record<string, any>;
	} catch (err) {
		cachedLibraryData = {};
		showSubprocessError('projspec library list', err);
	}
	return cachedLibraryData ?? {};
}

/**
 * Show a VS Code error notification for a failed subprocess, and open the
 * full stdout + stderr output in a read-only editor tab so the user can
 * inspect the details.
 */
async function showSubprocessError(label: string, err: unknown): Promise<void> {
	// SpawnSyncReturns (thrown by execSync on non-zero exit) carries stdout/stderr.
	// We also handle plain Error objects and unknown throws.
	let detail = '';
	if (err && typeof err === 'object') {
		const e = err as Record<string, any>;
		const stdout: string = typeof e['stdout'] === 'string' ? e['stdout']
			: Buffer.isBuffer(e['stdout']) ? e['stdout'].toString() : '';
		const stderr: string = typeof e['stderr'] === 'string' ? e['stderr']
			: Buffer.isBuffer(e['stderr']) ? e['stderr'].toString() : '';
		const msg: string = typeof e['message'] === 'string' ? e['message'] : '';
		const parts: string[] = [];
		if (msg)    { parts.push(`--- error ---\n${msg}`); }
		if (stdout) { parts.push(`--- stdout ---\n${stdout}`); }
		if (stderr) { parts.push(`--- stderr ---\n${stderr}`); }
		detail = parts.join('\n\n').trim();
	}
	if (!detail) { detail = String(err); }

	vscode.window.showErrorMessage(`projspec: ${label} failed. See editor tab for details.`);

	const doc = await vscode.workspace.openTextDocument({
		language: 'text',
		content: `projspec subprocess error: ${label}\n${'='.repeat(60)}\n\n${detail}\n`,
	});
	await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: false });
}

function escapeHtml(s: string): string {
	return String(s)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

/** Deterministic pastel colour from a string label */
function pastelColour(label: string): string {
	let h = 0;
	for (let i = 0; i < label.length; i++) { h = (h * 31 + label.charCodeAt(i)) >>> 0; }
	const hue = h % 360;
	return `hsl(${hue},55%,72%)`;
}

function runInTerminal(cmd: string): void {
	let terminal = vscode.window.terminals.find(t => t.name === 'projspec');
	if (!terminal) { terminal = vscode.window.createTerminal('projspec'); }
	terminal.show();
	terminal.sendText(cmd);
}

function getConfigPath(): string {
	const dir = process.env['PROJSPEC_CONFIG_DIR'] ?? path.join(os.homedir(), '.config', 'projspec');
	return path.join(dir, 'projspec.json');
}

async function openConfigFile(): Promise<void> {
	const cfgPath = getConfigPath();
	const dir = path.dirname(cfgPath);
	if (!fs.existsSync(dir)) { fs.mkdirSync(dir, { recursive: true }); }
	if (!fs.existsSync(cfgPath)) {
		const defaults = {
			scan_types: ['.py', '.yaml', '.yml', '.toml', '.json', '.md'],
			scan_max_files: 100,
			scan_max_size: 5000,
			remote_artifact_status: false,
			capture_artifact_output: true,
			preferred_install_methods: ['conda', 'pip'],
		};
		fs.writeFileSync(cfgPath, JSON.stringify(defaults, null, 2));
	}
	const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(cfgPath));
	await vscode.window.showTextDocument(doc, { preview: false });
}

function fsPathFromUrl(url: string): string {
	return url.startsWith('file://') ? url.slice(7) : url;
}

// ---------------------------------------------------------------------------
// Details webview
// ---------------------------------------------------------------------------

/**
 * Refresh or create the details panel.
 * selection: 'contents' | 'artifacts' | <specName>
 */
function showDetailsPanel(projectUrl: string, selection: string): void {
	const library = cachedLibraryData ?? {};
	const project = library[projectUrl];
	if (!project) { return; }

	const basename = projectUrl.split('/').pop() ?? projectUrl;

	const title = selection === 'contents' ? 'Contents'
		: selection === 'artifacts' ? 'Artifacts'
		: selection;

	if (!detailsPanel) {
		detailsPanel = vscode.window.createWebviewPanel(
			'projspecDetails',
			`${basename} — ${title}`,
			{ viewColumn: vscode.ViewColumn.Two, preserveFocus: true },
			{ enableScripts: true, retainContextWhenHidden: true }
		);
		if (extensionLogoUri) { detailsPanel.iconPath = extensionLogoUri; }
		detailsPanel.onDidDispose(() => {
			detailsPanel = undefined;
			detailsPanelState = undefined;
		});
		detailsPanel.webview.onDidReceiveMessage(msg => {
			if (msg.command === 'makeArtifact') {
				const qname: string = msg.qname;
				const projPath = fsPathFromUrl(projectUrl);
				runInTerminal(`projspec make ${qname} "${projPath}"`);
			}
		});
	} else {
		detailsPanel.reveal(vscode.ViewColumn.Two, true);
	}

	detailsPanelState = { projectUrl, selection };
	detailsPanel.title = `${basename} — ${title}`;
	detailsPanel.webview.html = buildDetailsHtml(basename, projectUrl, project, selection);
}

function buildDetailsHtml(
	basename: string,
	projectUrl: string,
	project: any,
	selection: string,
): string {
	const infoData = getInfoData();

	// Resolve what to display
	let panelTitle = '';
	let infoDoc = '';
	let infoLink = '';
	let showInfoArea = false;

	if (selection === 'contents') {
		panelTitle = 'Contents';
	} else if (selection === 'artifacts') {
		panelTitle = 'Artifacts';
	} else {
		panelTitle = selection;
		showInfoArea = true;
		const rec = infoData?.specs?.[selection];
		if (rec) { infoDoc = rec.doc ?? ''; infoLink = rec.link ?? ''; }
	}

	// Collect widgets
	let rawItems: Array<{ klass: string; name?: string; data: any; isArtifact: boolean }> = [];

	if (selection === 'contents') {
		rawItems = collectItems(project.contents ?? {}, false);
	} else if (selection === 'artifacts') {
		rawItems = collectItems(project.artifacts ?? {}, true);
	} else {
		// spec view — show _contents and _artifacts of that spec
		const specData = (project.specs ?? {})[selection] ?? {};
		rawItems = [
			...collectItems(specData._contents ?? {}, false),
			...collectItems(specData._artifacts ?? {}, true),
		];
	}

	const widgetsHtml = rawItems.map(item => renderWidget(item, infoData)).join('\n');

	const infoAreaHtml = showInfoArea ? `
		<details id="details-info" class="info-area" open>
			<summary class="info-summary">${escapeHtml(panelTitle)}</summary>
			<div class="info-body">
				${infoDoc ? `<p>${escapeHtml(infoDoc)}</p>` : ''}
				${infoLink ? `<p><a href="${escapeHtml(infoLink)}" class="ext-link">${escapeHtml(infoLink)}</a></p>` : ''}
				${!infoDoc && !infoLink ? '<p><em>No documentation available.</em></p>' : ''}
			</div>
		</details>` : '';

	return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(panelTitle)}</title>
<style>
  body{margin:0;padding:0;font-family:var(--vscode-font-family);font-size:var(--vscode-font-size);color:var(--vscode-foreground);background:var(--vscode-editor-background);}
  h1.panel-title{margin:0;font-size:15px;font-weight:700;padding:10px 12px 4px;border-bottom:1px solid var(--vscode-panel-border);}
  .info-area{border-bottom:1px solid var(--vscode-panel-border);padding:0 12px;}
  .info-summary{cursor:pointer;font-weight:600;padding:6px 0;list-style:none;user-select:none;}
  .info-summary::-webkit-details-marker{display:none;}
  .info-body{padding:4px 0 8px;font-size:12px;color:var(--vscode-descriptionForeground);}
  .ext-link{color:var(--vscode-textLink-foreground);word-break:break-all;}
  .ext-link:hover{text-decoration:underline;}
  #widgets{padding:8px 10px;overflow-y:auto;}
  .widget{border:1px solid var(--vscode-panel-border);border-radius:6px;margin-bottom:8px;background:var(--vscode-editor-background);position:relative;}
  .widget-header{display:flex;align-items:center;padding:6px 10px;gap:6px;border-bottom:1px solid var(--vscode-panel-border);}
  .widget-klass{font-weight:600;flex:1;}
  .widget-name{font-size:11px;color:var(--vscode-descriptionForeground);}
  .btn-make,.btn-info{display:none;border:none;border-radius:3px;cursor:pointer;font-size:11px;padding:2px 8px;font-family:inherit;}
  .widget:hover .btn-make,.widget:hover .btn-info{display:inline-block;}
  .btn-make{background:var(--vscode-button-background);color:var(--vscode-button-foreground);margin-right:4px;}
  .btn-make:hover{background:var(--vscode-button-hoverBackground);}
  .btn-info{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);border-radius:50%;width:20px;height:20px;padding:0;display:none;align-items:center;justify-content:center;}
  .widget:hover .btn-info{display:flex;}
  .btn-info:hover{background:var(--vscode-button-secondaryHoverBackground);}
  .tree-body{padding:4px 10px 8px;}
  .tree-ul{list-style:none;margin:0;padding-left:16px;}
  .tree-ul.root{padding-left:0;}
  .tree-li{margin:1px 0;}
  .tree-row{display:flex;align-items:baseline;gap:4px;cursor:default;border-radius:3px;padding:1px 3px;line-height:1.6;}
  .tree-row:hover{background:var(--vscode-list-hoverBackground);}
  .expander{width:14px;flex-shrink:0;font-size:10px;cursor:pointer;user-select:none;color:var(--vscode-descriptionForeground);}
  .ghost-expander{width:14px;flex-shrink:0;display:inline-block;}
  .tree-key{color:var(--vscode-symbolIcon-variableForeground);font-weight:500;flex-shrink:0;}
  .tree-val{color:var(--vscode-descriptionForeground);margin-left:4px;word-break:break-all;}
  .tree-enum{color:var(--vscode-symbolIcon-enumeratorForeground,#4fc1ff);font-style:italic;}
  .tree-null{color:var(--vscode-descriptionForeground);font-style:italic;opacity:.7;}
  .tree-bool{color:var(--vscode-debugTokenExpression-boolean,#569cd6);}
  .tree-empty{color:var(--vscode-descriptionForeground);opacity:.6;}
  .subtree{display:none;}
  .subtree.open{display:block;}
  /* info popup */
  #info-popup{position:fixed;background:var(--vscode-editor-background);border:1px solid var(--vscode-panel-border);border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.3);padding:14px;max-width:360px;min-width:220px;z-index:999;display:none;font-size:12px;line-height:1.5;}
  #info-popup.show{display:block;}
  #info-popup h4{margin:0 0 6px;font-size:13px;}
  .popup-link{color:var(--vscode-textLink-foreground);word-break:break-all;}
</style>
</head>
<body>
<h1 class="panel-title">${escapeHtml(panelTitle)}</h1>
${infoAreaHtml}
<div id="widgets">${widgetsHtml}</div>
<div id="info-popup"></div>
<script>
const vscode = acquireVsCodeApi();
// expand/collapse tree rows
document.addEventListener('click', e => {
  const exp = e.target.closest('.expander');
  if (exp) {
    const li = exp.closest('.tree-li');
    const sub = li && li.querySelector(':scope > .subtree');
    if (sub) { sub.classList.toggle('open'); exp.textContent = sub.classList.contains('open') ? '▾' : '▸'; }
    return;
  }
  // hide popup when clicking elsewhere
  if (!e.target.closest('#info-popup') && !e.target.closest('.btn-info')) {
    document.getElementById('info-popup').classList.remove('show');
  }
});
// make buttons
document.addEventListener('click', e => {
  const btn = e.target.closest('.btn-make');
  if (btn) { vscode.postMessage({ command: 'makeArtifact', qname: btn.dataset.qname }); }
});
// info buttons
document.addEventListener('click', e => {
  const btn = e.target.closest('.btn-info');
  if (!btn) { return; }
  e.stopPropagation();
  const popup = document.getElementById('info-popup');
  const doc = btn.dataset.doc || '';
  const link = btn.dataset.link || '';
  const title = btn.dataset.title || '';
  popup.innerHTML = '<h4>' + title + '</h4>' +
    (doc ? '<p>' + doc + '</p>' : '') +
    (link ? '<p><a class="popup-link" href="' + link + '">' + link + '</a></p>' : '') +
    (!doc && !link ? '<p><em>No information available.</em></p>' : '');
  // position to the left of the button
  const rect = btn.getBoundingClientRect();
  popup.classList.add('show');
  const pw = popup.offsetWidth || 260;
  let left = rect.left - pw - 8;
  if (left < 4) { left = rect.right + 8; }
  let top = rect.top - 10;
  const ph = popup.offsetHeight || 120;
  if (top + ph > window.innerHeight - 8) { top = window.innerHeight - ph - 8; }
  popup.style.left = left + 'px';
  popup.style.top = top + 'px';
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { document.getElementById('info-popup').classList.remove('show'); }
});
</script>
</body>
</html>`;
}

/**
 * Extract the display typename from a klass field.
 * klass is always a 2-element array [category, typename], e.g. ["content", "environment"].
 * We want only the typename (index 1).
 */
function klassTypeName(klass: any): string {
	if (Array.isArray(klass) && klass.length >= 2) { return String(klass[1]); }
	if (Array.isArray(klass) && klass.length === 1) { return String(klass[0]); }
	return String(klass);
}

/**
 * Convert the raw JSON subtree (contents or artifacts dict) into widget data.
 * Each widget has a klass typename, optional name, the raw data object, and isArtifact flag.
 */
function collectItems(
	raw: any,
	isArtifact: boolean,
): Array<{ klass: string; name?: string; data: any; isArtifact: boolean }> {
	if (!raw || typeof raw !== 'object') { return []; }
	const out: Array<{ klass: string; name?: string; data: any; isArtifact: boolean }> = [];
	for (const [key, value] of Object.entries(raw as Record<string, any>)) {
		if (value && typeof value === 'object' && !Array.isArray(value)) {
			if ('klass' in value) {
				// Single item, no name
				out.push({ klass: klassTypeName(value.klass), data: value, isArtifact });
			} else {
				// Check if each nested value has a klass → named items
				const entries = Object.entries(value);
				const allHaveKlass = entries.length > 0 && entries.every(([, v]) => v && typeof v === 'object' && 'klass' in (v as any));
				if (allHaveKlass) {
					for (const [name, item] of entries) {
						out.push({ klass: klassTypeName((item as any).klass), name, data: item, isArtifact });
					}
				} else {
					// Fallback: treat key as klass
					out.push({ klass: key, data: value, isArtifact });
				}
			}
		} else if (Array.isArray(value)) {
			// List of items each with a klass
			for (const item of value) {
				if (item && typeof item === 'object' && 'klass' in item) {
					out.push({ klass: klassTypeName(item.klass), data: item, isArtifact });
				}
			}
		} else {
			out.push({ klass: key, data: value, isArtifact });
		}
	}
	return out;
}

/** Derive qname for an artifact widget from its data */
function artifactQname(item: { klass: string; name?: string; data: any }): string {
	return item.name ? `${item.klass}.${item.name}` : item.klass;
}

function renderWidget(
	item: { klass: string; name?: string; data: any; isArtifact: boolean },
	infoData: InfoData | null,
): string {
	const klassLabel = item.klass;
	const nameLabel = item.name ?? '';
	const infoRec = item.isArtifact
		? (infoData?.artifact?.[item.klass] ?? null)
		: (infoData?.content?.[item.klass] ?? null);
	const doc = infoRec?.doc ?? '';
	const link = infoRec?.link ?? '';
	const qname = item.isArtifact ? artifactQname(item) : '';
	const enumMembers = infoData?.enumMembers ?? {};

	const makeBtn = item.isArtifact
		? `<button class="btn-make" data-qname="${escapeHtml(qname)}" title="Make">Make</button>`
		: '';
	const infoBtn = `<button class="btn-info" data-title="${escapeHtml(klassLabel)}" data-doc="${escapeHtml(doc)}" data-link="${escapeHtml(link)}" title="Info">i</button>`;

	const treeHtml = renderDataTree(item.data, true, enumMembers);

	return `<div class="widget">
  <div class="widget-header">
    <span class="widget-klass">${escapeHtml(klassLabel)}</span>
    ${nameLabel ? `<span class="widget-name">${escapeHtml(nameLabel)}</span>` : ''}
    <span style="flex:1"></span>
    ${makeBtn}
    ${infoBtn}
  </div>
  <div class="tree-body">${treeHtml}</div>
</div>`;
}

const SKIP_WIDGET_KEYS = new Set(['klass', 'proc', '_html']);

/**
 * Render a value as an indented YAML-style tree.
 * Handles: scalars, lists, dicts, and enum objects {klass:["enum","x"], value:N}.
 */
function renderDataTree(
	obj: any,
	isRoot: boolean = true,
	enumMembers: Record<string, Record<string, string>> = {},
): string {
	// Enum object: { klass: ["enum", "typename"], value: N }
	if (obj && typeof obj === 'object' && !Array.isArray(obj)
		&& Array.isArray(obj.klass) && obj.klass[0] === 'enum') {
		const enumType: string = obj.klass[1] ?? '';
		const rawVal: string = String(obj.value);
		const memberName: string = enumMembers[enumType]?.[rawVal] ?? rawVal;
		return `<span class="tree-val tree-enum">${escapeHtml(memberName)}</span>`;
	}

	if (obj === null || obj === undefined) {
		return `<span class="tree-val tree-null">null</span>`;
	}
	if (typeof obj === 'boolean') {
		return `<span class="tree-val tree-bool">${obj}</span>`;
	}
	if (typeof obj !== 'object') {
		return `<span class="tree-val">${escapeHtml(String(obj))}</span>`;
	}

	if (Array.isArray(obj)) {
		if (obj.length === 0) { return `<span class="tree-val tree-empty">[]</span>`; }
		const items = obj.map(v => {
			const isNested = v !== null && typeof v === 'object';
			if (isNested) {
				const child = renderDataTree(v, false, enumMembers);
				// Enum objects inline; others get a collapsible row
				if (child.startsWith('<span')) {
					// Already rendered inline (enum or scalar-like)
					return `<li class="tree-li"><div class="tree-row"><span class="ghost-expander"></span>${child}</div></li>`;
				}
				return `<li class="tree-li">
  <div class="tree-row"><span class="expander">▸</span></div>
  <ul class="tree-ul subtree">${child}</ul>
</li>`;
			}
			return `<li class="tree-li"><div class="tree-row"><span class="ghost-expander"></span>${renderDataTree(v, false, enumMembers)}</div></li>`;
		}).join('');
		return `<ul class="tree-ul${isRoot ? ' root' : ''}">${items}</ul>`;
	}

	// Plain object (dict)
	const entries = Object.entries(obj).filter(([k]) => !SKIP_WIDGET_KEYS.has(k));
	if (entries.length === 0) { return ''; }

	const items = entries.map(([k, v]) => {
		const renderedVal = renderDataTree(v, false, enumMembers);
		const isInline = renderedVal.startsWith('<span');  // scalars and enums render as <span>
		if (isInline) {
			// key: value on one line
			return `<li class="tree-li"><div class="tree-row"><span class="ghost-expander"></span><span class="tree-key">${escapeHtml(k)}:</span>${renderedVal}</div></li>`;
		}
		// key on its own line, children collapsible below
		return `<li class="tree-li">
  <div class="tree-row"><span class="expander">▸</span><span class="tree-key">${escapeHtml(k)}:</span></div>
  <ul class="tree-ul subtree">${renderedVal}</ul>
</li>`;
	}).join('');

	return `<ul class="tree-ul${isRoot ? ' root' : ''}">${items}</ul>`;
}

// ---------------------------------------------------------------------------
// Library (left panel) HTML
// ---------------------------------------------------------------------------

function buildLibraryHtml(library: Record<string, any>, infoData: InfoData | null): string {
	// Spec names that have create:true
	const creatableSpecs = infoData
		? Object.entries(infoData.specs)
			.filter(([, v]) => v.create === true)
			.map(([k]) => k)
		: [];

	const projectWidgets = Object.entries(library).map(([url, project]) => {
		return buildProjectWidget(url, project, creatableSpecs, infoData);
	}).join('\n');

	return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project Library</title>
<style>
  *{box-sizing:border-box;}
  body{margin:0;padding:0;font-family:var(--vscode-font-family);font-size:var(--vscode-font-size);color:var(--vscode-foreground);background:var(--vscode-editor-background);display:flex;flex-direction:column;height:100vh;overflow:hidden;}
  /* Top bar */
  .topbar{display:flex;align-items:center;gap:6px;padding:6px 8px;border-bottom:1px solid var(--vscode-panel-border);flex-shrink:0;}
  .topbar-btn{padding:3px 10px;border-radius:3px;border:1px solid var(--vscode-button-border);cursor:pointer;font-family:inherit;font-size:12px;background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);}
  .topbar-btn:hover{background:var(--vscode-button-secondaryHoverBackground);}
  /* Search bar */
  .searchbar{padding:5px 8px;border-bottom:1px solid var(--vscode-panel-border);flex-shrink:0;display:flex;align-items:center;gap:4px;}
  #search-input{flex:1;padding:3px 6px;background:var(--vscode-settings-textInputBackground);color:var(--vscode-settings-textInputForeground);border:1px solid var(--vscode-settings-textInputBorder);border-radius:2px;font-family:inherit;font-size:inherit;}
  #search-input:focus{outline:1px solid var(--vscode-focusBorder);}
  #search-clear{background:none;border:none;cursor:pointer;color:var(--vscode-foreground);opacity:.6;font-size:13px;padding:0 3px;display:none;}
  #search-clear:hover{opacity:1;}
  /* Projects list */
  #projects-list{flex:1;overflow-y:auto;padding:8px;}
  /* Project widget */
  .proj-widget{border:1px solid var(--vscode-panel-border);border-radius:6px;margin-bottom:10px;background:var(--vscode-editor-background);position:relative;}
  .proj-widget-header{display:flex;align-items:flex-start;padding:8px 10px 4px;gap:6px;}
  .proj-name{font-weight:700;font-size:13px;flex:1;word-break:break-all;}
  .proj-url{font-size:10px;color:var(--vscode-descriptionForeground);padding:0 10px 4px;word-break:break-all;}
  .proj-storage{font-size:10px;color:var(--vscode-descriptionForeground);padding:0 10px 4px;word-break:break-all;}
  .proj-chips{display:flex;flex-wrap:wrap;gap:5px;padding:4px 10px 8px;}
  .chip{padding:2px 10px;border-radius:12px;font-size:11px;cursor:pointer;font-weight:500;border:none;font-family:inherit;white-space:nowrap;}
  .chip:hover{opacity:.8;}
  /* Kebab button */
  .kebab-btn{background:none;border:none;cursor:pointer;color:var(--vscode-foreground);font-size:18px;line-height:1;padding:0 4px;opacity:.6;flex-shrink:0;}
  .kebab-btn:hover{opacity:1;}
  /* Kebab dropdown */
  .kebab-menu{position:fixed;background:var(--vscode-menu-background);border:1px solid var(--vscode-menu-border);border-radius:4px;box-shadow:0 4px 12px rgba(0,0,0,.4);padding:4px 0;z-index:3000;display:none;min-width:170px;}
  .kebab-menu.show{display:block;}
  .km-item{padding:5px 16px;cursor:pointer;color:var(--vscode-menu-foreground);font-size:var(--vscode-font-size);white-space:nowrap;}
  .km-item:hover{background:var(--vscode-menu-selectionBackground);color:var(--vscode-menu-selectionForeground);}
  .km-item.disabled{opacity:.4;cursor:default;pointer-events:none;}
  .km-separator{border:none;border-top:1px solid var(--vscode-menu-separatorBackground);margin:3px 0;}
  .km-sub-label{padding:5px 16px 3px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--vscode-descriptionForeground);pointer-events:none;}
  /* Loading overlay */
  .loading-overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;align-items:center;justify-content:center;z-index:4000;cursor:wait;}
  .loading-overlay.show{display:flex;}
  .spinner{width:28px;height:28px;border:3px solid var(--vscode-foreground);border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;opacity:.8;}
  @keyframes spin{to{transform:rotate(360deg);}}
  /* Create-spec modal */
  .modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:5000;}
  .modal-overlay.show{display:flex;}
  .modal-box{background:var(--vscode-editor-background);border:1px solid var(--vscode-panel-border);border-radius:6px;padding:20px;width:320px;max-width:90%;box-shadow:0 4px 16px rgba(0,0,0,.5);}
  .modal-title{margin:0 0 14px;font-size:14px;font-weight:700;}
  .modal-input{width:100%;padding:5px 8px;background:var(--vscode-settings-textInputBackground);color:var(--vscode-settings-textInputForeground);border:1px solid var(--vscode-settings-textInputBorder);border-radius:2px;font-family:inherit;font-size:inherit;}
  .modal-input:focus{outline:1px solid var(--vscode-focusBorder);}
  .ac-list{position:relative;background:var(--vscode-editor-background);border:1px solid var(--vscode-panel-border);border-top:none;max-height:140px;overflow-y:auto;display:none;}
  .ac-list.show{display:block;}
  .ac-item{padding:5px 10px;cursor:pointer;font-size:12px;}
  .ac-item:hover,.ac-item.active{background:var(--vscode-list-hoverBackground);}
  .modal-btns{display:flex;justify-content:flex-end;gap:8px;margin-top:16px;}
  .modal-btn{padding:5px 14px;border-radius:2px;border:1px solid var(--vscode-button-border);cursor:pointer;font-family:inherit;font-size:13px;}
  .modal-btn-primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground);}
  .modal-btn-primary:hover{background:var(--vscode-button-hoverBackground);}
  .modal-btn-secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);}
  .modal-btn-secondary:hover{background:var(--vscode-button-secondaryHoverBackground);}
</style>
</head>
<body>
<!-- Top buttons -->
<div class="topbar">
  <button class="topbar-btn" id="btn-add">Add</button>
  <button class="topbar-btn" id="btn-reload">Reload</button>
  <button class="topbar-btn" id="btn-configure">Configure</button>
</div>
<!-- Search -->
<div class="searchbar">
  <input id="search-input" type="text" placeholder="Search projects…" autocomplete="off">
  <button id="search-clear" title="Clear">&#x2715;</button>
</div>
<!-- Project cards -->
<div id="projects-list">
  ${projectWidgets || '<p style="color:var(--vscode-descriptionForeground);padding:10px;">No projects in library. Use Add or Reload.</p>'}
</div>

<!-- Loading overlay -->
<div id="loading-overlay" class="loading-overlay"><div class="spinner"></div></div>

<!-- Kebab menu -->
<div id="kebab-menu" class="kebab-menu"></div>

<!-- Create-spec modal -->
<div id="create-modal" class="modal-overlay">
  <div class="modal-box">
    <h3 class="modal-title">Create spec</h3>
    <input id="spec-input" class="modal-input" type="text" placeholder="Spec type…" autocomplete="off">
    <div id="ac-list" class="ac-list"></div>
    <div class="modal-btns">
      <button class="modal-btn modal-btn-secondary" id="modal-cancel">Cancel</button>
      <button class="modal-btn modal-btn-primary" id="modal-ok">Create</button>
    </div>
  </div>
</div>

<script>
(function(){
const vscode = acquireVsCodeApi();

// ---------- loading overlay ----------
function setLoading(v){ document.getElementById('loading-overlay').classList.toggle('show', v); }

// ---------- top buttons ----------
document.getElementById('btn-add').addEventListener('click', () => {
  vscode.postMessage({ command: 'add' });
});
document.getElementById('btn-reload').addEventListener('click', () => {
  setLoading(true);
  vscode.postMessage({ command: 'reload' });
});
document.getElementById('btn-configure').addEventListener('click', () => {
  vscode.postMessage({ command: 'configure' });
});

// ---------- search ----------
const searchInput = document.getElementById('search-input');
const searchClear = document.getElementById('search-clear');
searchInput.addEventListener('input', () => {
  const term = searchInput.value.toLowerCase();
  searchClear.style.display = term ? 'block' : 'none';
  document.querySelectorAll('.proj-widget').forEach(w => {
    const text = w.textContent.toLowerCase();
    w.style.display = text.includes(term) ? '' : 'none';
  });
});
searchClear.addEventListener('click', () => {
  searchInput.value = '';
  searchClear.style.display = 'none';
  document.querySelectorAll('.proj-widget').forEach(w => { w.style.display = ''; });
  searchInput.focus();
});

// ---------- chip clicks ----------
document.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (chip) {
    const url = chip.dataset.url;
    const sel = chip.dataset.sel;
    if (url && sel) {
      vscode.postMessage({ command: 'selectChip', projectUrl: url, selection: sel });
    }
    return;
  }
});

// ---------- kebab menu ----------
let kebabState = null;  // { url, isLocal, specNames: [] }
const kebabMenu = document.getElementById('kebab-menu');

document.addEventListener('click', e => {
  const btn = e.target.closest('.kebab-btn');
  if (btn) {
    e.stopPropagation();
    kebabState = JSON.parse(btn.dataset.state);
    buildKebabMenu(kebabState);
    const rect = btn.getBoundingClientRect();
    kebabMenu.style.top = (rect.bottom + 2) + 'px';
    kebabMenu.style.left = (rect.right - kebabMenu.offsetWidth) + 'px';
    // Ensure it doesn't overflow right
    const mw = kebabMenu.offsetWidth || 180;
    let left = rect.right - mw;
    if (left < 4) { left = 4; }
    kebabMenu.style.left = left + 'px';
    kebabMenu.classList.add('show');
    return;
  }
  if (!kebabMenu.contains(e.target)) { hideKebab(); }
});

function hideKebab(){ kebabMenu.classList.remove('show'); }

function buildKebabMenu(state){
  kebabMenu.innerHTML = '';
  if (state.isLocal) {
    addSubLabel('Open with…');
    addKebabItem('VSCode', () => { vscode.postMessage({ command: 'openVSCode', url: state.url }); });
    addKebabItem('System file browser', () => { vscode.postMessage({ command: 'openFileBrowser', url: state.url }); });
    addKebabItem('PyCharm', () => { vscode.postMessage({ command: 'openPyCharm', url: state.url }); });
    addKebabItem('Jupyter', () => { vscode.postMessage({ command: 'openJupyter', url: state.url }); });
    addSeparator();
    addKebabItem('Rescan', () => { setLoading(true); vscode.postMessage({ command: 'rescan', url: state.url }); });
    addKebabItem('Create spec', () => { showCreateSpecModal(state); });
    addKebabItem('Remove from library', () => { setLoading(true); vscode.postMessage({ command: 'remove', url: state.url }); });
  } else {
    addKebabItem('Copy to local', () => {}, true);
    addKebabItem('Rescan', () => { setLoading(true); vscode.postMessage({ command: 'rescan', url: state.url }); });
    addKebabItem('Remove from library', () => { setLoading(true); vscode.postMessage({ command: 'remove', url: state.url }); });
  }
}

function addSubLabel(text){
  const el = document.createElement('div');
  el.className = 'km-sub-label';
  el.textContent = text;
  kebabMenu.appendChild(el);
}
function addSeparator(){
  const el = document.createElement('hr');
  el.className = 'km-separator';
  kebabMenu.appendChild(el);
}
function addKebabItem(label, action, disabled=false){
  const el = document.createElement('div');
  el.className = 'km-item' + (disabled ? ' disabled' : '');
  el.textContent = label;
  if (!disabled) { el.addEventListener('click', () => { hideKebab(); action(); }); }
  kebabMenu.appendChild(el);
}

// ---------- create-spec modal ----------
let createSpecState = null;
const createModal = document.getElementById('create-modal');
const specInput = document.getElementById('spec-input');
const acList = document.getElementById('ac-list');
let acActive = -1;

function showCreateSpecModal(state){
  createSpecState = state;
  specInput.value = '';
  acActive = -1;
  renderAc('');
  createModal.classList.add('show');
  specInput.focus();
}

specInput.addEventListener('input', () => { acActive = -1; renderAc(specInput.value); });
specInput.addEventListener('keydown', e => {
  const items = acList.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown'){ acActive = Math.min(acActive+1, items.length-1); updAc(items); e.preventDefault(); }
  else if (e.key === 'ArrowUp'){ acActive = Math.max(acActive-1, -1); updAc(items); e.preventDefault(); }
  else if (e.key === 'Enter'){
    if (acActive >= 0 && items[acActive]){ specInput.value = items[acActive].textContent; acList.classList.remove('show'); }
    else { doCreateSpec(); }
  }
  else if (e.key === 'Escape'){ closeCreateModal(); }
});

function renderAc(filter){
  const specs = (createSpecState && createSpecState.specNames) ? createSpecState.specNames : [];
  const filtered = specs.filter(s => s.toLowerCase().includes(filter.toLowerCase()));
  acList.innerHTML = '';
  filtered.forEach(s => {
    const el = document.createElement('div');
    el.className = 'ac-item';
    el.textContent = s;
    el.addEventListener('mousedown', ev => { ev.preventDefault(); specInput.value = s; acList.classList.remove('show'); });
    acList.appendChild(el);
  });
  acList.classList.toggle('show', filtered.length > 0);
}

function updAc(items){
  items.forEach((it, i) => it.classList.toggle('active', i === acActive));
  if (acActive >= 0 && items[acActive]){ items[acActive].scrollIntoView({ block: 'nearest' }); }
}

document.getElementById('modal-cancel').addEventListener('click', closeCreateModal);
document.getElementById('modal-ok').addEventListener('click', doCreateSpec);
function closeCreateModal(){ createModal.classList.remove('show'); }
function doCreateSpec(){
  const spec = specInput.value.trim();
  if (!spec || !createSpecState) { specInput.focus(); return; }
  setLoading(true);
  vscode.postMessage({ command: 'createSpec', url: createSpecState.url, spec });
  closeCreateModal();
}

// Close modal on overlay click
createModal.addEventListener('click', e => { if (e.target === createModal){ closeCreateModal(); } });

document.addEventListener('keydown', e => {
  if (e.key === 'Escape'){ closeCreateModal(); hideKebab(); }
});

// Handle messages from extension (e.g., reload response)
window.addEventListener('message', ev => {
  const msg = ev.data;
  if (msg.command === 'reloadDone') { setLoading(false); }
});

})();
</script>
</body>
</html>`;
}

function buildProjectWidget(
	url: string,
	project: any,
	creatableSpecs: string[],
	infoData: InfoData | null,
): string {
	const basename = url.split('/').pop() ?? url;
	const isLocal = url.startsWith('file://');
	const fsPath = isLocal ? fsPathFromUrl(url) : null;
	const displayUrl = fsPath ?? url;

	// Chips
	const chips: Array<{ label: string; sel: string }> = [];
	const contents = project.contents ?? {};
	const artifacts = project.artifacts ?? {};
	const specs = project.specs ?? {};

	const contCount = Object.keys(contents).length;
	const artCount = Object.keys(artifacts).length;
	if (contCount > 0) { chips.push({ label: `Contents <${contCount}>`, sel: 'contents' }); }
	if (artCount > 0) { chips.push({ label: `Artifacts <${artCount}>`, sel: 'artifacts' }); }
	for (const specName of Object.keys(specs)) {
		chips.push({ label: specName, sel: specName });
	}

	const chipsHtml = chips.map(c => {
		const bg = pastelColour(c.label);
		return `<button class="chip" style="background:${bg};color:#222;" data-url="${escapeHtml(url)}" data-sel="${escapeHtml(c.sel)}">${escapeHtml(c.label)}</button>`;
	}).join('');

	// Storage options
	const storageOpts = project.storage_options;
	const storageHtml = storageOpts && typeof storageOpts === 'object' && Object.keys(storageOpts).length > 0
		? `<div class="proj-storage">${escapeHtml(JSON.stringify(storageOpts))}</div>`
		: '';

	// Specs already present in the project
	const presentSpecs = Object.keys(specs);
	// Specs available for creation: creatable AND not already present
	const availableSpecs = creatableSpecs.filter(s => !presentSpecs.includes(s));

	const kebabState = JSON.stringify({ url, isLocal, specNames: availableSpecs })
		.replace(/"/g, '&quot;');

	return `<div class="proj-widget">
  <div class="proj-widget-header">
    <span class="proj-name">${escapeHtml(basename)}</span>
    <button class="kebab-btn" data-state="${kebabState}" title="More actions">⋮</button>
  </div>
  <div class="proj-url">${escapeHtml(displayUrl)}</div>
  ${storageHtml}
  <div class="proj-chips">${chipsHtml}</div>
</div>`;
}

// ---------------------------------------------------------------------------
// activate()
// ---------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext): void {
	extensionLogoUri = vscode.Uri.joinPath(context.extensionUri, 'logo.png');

	context.subscriptions.push(
		vscode.commands.registerCommand('projspec.showTree', async () => {
			if (libraryPanel) {
				libraryPanel.reveal(vscode.ViewColumn.One);
				return;
			}

			const panel = vscode.window.createWebviewPanel(
				'projspecLibrary',
				'Project Library',
				vscode.ViewColumn.One,
				{ enableScripts: true, retainContextWhenHidden: true }
			);
			libraryPanel = panel;
			if (extensionLogoUri) { panel.iconPath = extensionLogoUri; }
			panel.onDidDispose(() => { libraryPanel = undefined; });

			// Initial load
			panel.webview.html = buildLoadingHtml();
			const library = loadLibraryData();
			const info = getInfoData();
			panel.webview.html = buildLibraryHtml(library, info);

			panel.webview.onDidReceiveMessage(async (msg: any) => {
				switch (msg.command as string) {

					case 'add': {
						const uris = await vscode.window.showOpenDialog({
							canSelectFolders: true,
							canSelectFiles: false,
							canSelectMany: false,
							openLabel: 'Add to Library',
						});
						if (!uris || uris.length === 0) { break; }
						const folderPath = uris[0].fsPath;
						try {
							execSync(`projspec scan --library "${folderPath}"`, { stdio: 'pipe', encoding: 'utf-8' });
						} catch (err) {
							await showSubprocessError(`scan ${folderPath}`, err);
						}
						reloadLibraryPanel(panel);
						break;
					}

					case 'reload': {
						reloadLibraryPanel(panel);
						break;
					}

					case 'configure': {
						await openConfigFile();
						break;
					}

					case 'selectChip': {
						showDetailsPanel(msg.projectUrl as string, msg.selection as string);
						break;
					}

					case 'openVSCode': {
						const p = fsPathFromUrl(msg.url as string);
						await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(p), { forceNewWindow: true });
						break;
					}

					case 'openFileBrowser': {
						const p = fsPathFromUrl(msg.url as string);
						await vscode.env.openExternal(vscode.Uri.file(p));
						break;
					}

					case 'openPyCharm': {
						const p = fsPathFromUrl(msg.url as string);
						runInTerminal(`pycharm "${p}" nosplash dontReopenProjects`);
						break;
					}

					case 'openJupyter': {
						const p = fsPathFromUrl(msg.url as string);
						runInTerminal(`jupyter lab "${p}"`);
						break;
					}

					case 'rescan': {
						const p = fsPathFromUrl(msg.url as string);
						try {
							execSync(`projspec scan --library "${p}"`, { stdio: 'pipe', encoding: 'utf-8' });
						} catch (err) {
							await showSubprocessError(`rescan ${p}`, err);
						}
						reloadLibraryPanel(panel);
						break;
					}

					case 'createSpec': {
						const p = fsPathFromUrl(msg.url as string);
						try {
							const out = execSync(`projspec create ${msg.spec} "${p}"`, { stdio: 'pipe', encoding: 'utf-8' });
							// Open any created files
							const files = out.split('\n').map((f: string) => f.trim()).filter((f: string) => f.length > 0);
							for (const file of files) {
								const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(file));
								await vscode.window.showTextDocument(doc, { preview: false });
							}
						} catch (err) {
							await showSubprocessError(`create ${msg.spec} in ${p}`, err);
						}
						reloadLibraryPanel(panel);
						break;
					}

					case 'remove': {
						const urlToRemove = msg.url as string;
						try {
							execSync(`projspec library delete "${urlToRemove}"`, { stdio: 'pipe', encoding: 'utf-8' });
						} catch (err) {
							await showSubprocessError(`library delete ${urlToRemove}`, err);
						}
						reloadLibraryPanel(panel);
						break;
					}
				}
			}, undefined, context.subscriptions);
		})
	);
}

function buildLoadingHtml(): string {
	return `<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:var(--vscode-editor-background);}
  .spinner{width:32px;height:32px;border:3px solid var(--vscode-foreground);border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;opacity:.7;}
  @keyframes spin{to{transform:rotate(360deg);}}
</style></head><body><div class="spinner"></div></body></html>`;
}

function reloadLibraryPanel(panel: vscode.WebviewPanel): void {
	panel.webview.html = buildLoadingHtml();
	const library = loadLibraryData();
	const info = getInfoData();
	panel.webview.html = buildLibraryHtml(library, info);
	panel.webview.postMessage({ command: 'reloadDone' });
}

// This method is called when your extension is deactivated
export function deactivate(): void {}
