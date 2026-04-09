// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { execSync } from "node:child_process";

interface TreeNode {
	key: string;
	children?: TreeNode[];
	data?: any;
	tooltip?: string;
	infoData?: string | null; // Store info data for popup, allowing null
	isProject?: boolean;
	projectUrl?: string;
	itemType?: string; // Type of item: 'content', 'artifact', 'spec'
	qname?: string; // Full qname for artifacts
}

let cachedInfo: { specs: Record<string, { doc: string | null; link: string }>; content: Record<string, { doc: string | null; link: string }>; artifact: Record<string, { doc: string | null; link: string }> } | null = null;
let cachedLibraryData: Record<string, any> | null = null;
let detailsPanel: vscode.WebviewPanel | undefined = undefined;
let detailsPanelProjectUrl: string | undefined = undefined;
let extensionLogoUri: vscode.Uri | undefined = undefined;

function getInfoData(): { specs: Record<string, { doc: string | null; link: string }>; content: Record<string, { doc: string | null; link: string }>; artifact: Record<string, { doc: string | null; link: string }> } | null {
	if (cachedInfo === null) {
		try {
			const out = execSync("projspec info", { stdio: 'pipe', encoding: 'utf-8' });
			cachedInfo = JSON.parse(out);
		} catch (error) {
			cachedInfo = null;
		}
	}
	return cachedInfo;
}

function buildTooltip(doc: string | null, link: string): string {
	const info = { doc: doc || "", link: link || "" };
	return JSON.stringify(info);
}

function buildTreeNodes(projectUrl: string, project: any): TreeNode[] {
	const projectChildren: TreeNode[] = [];
	const infoData = getInfoData();

	// Top-level contents
	if (project.contents && Object.keys(project.contents).length > 0) {
		for (const [name, _] of Object.entries(project.contents)) {
			const basename = name.split('/').pop() || name;
			const contentType = basename.split('.')[0];
			const info = infoData?.content?.[contentType];
			const infoText = info ? buildTooltip(info.doc, info.link) : null;
			projectChildren.push({
				key: basename,
				infoData: infoText,
				projectUrl,
				itemType: 'content'
			});
		}
	}

	// Top-level artifacts
	if (project.artifacts && Object.keys(project.artifacts).length > 0) {
		for (const [artifactType, artifactData] of Object.entries(project.artifacts)) {
			const info = infoData?.artifact?.[artifactType];
			const infoText = info ? buildTooltip(info.doc, info.link) : null;

			if (typeof artifactData === 'string') {
				projectChildren.push({
					key: artifactType,
					infoData: infoText,
					projectUrl,
					itemType: 'artifact',
					qname: artifactType
				});
			} else if (artifactData && typeof artifactData === 'object') {
				// Multiple artifacts of same type
				for (const [name, _] of Object.entries(artifactData as Record<string, any>)) {
					projectChildren.push({
						key: `${artifactType}.${name}`,
						infoData: infoText,
						projectUrl,
						itemType: 'artifact',
						qname: `${artifactType}.${name}`
					});
				}
			}
		}
	}

	// Specs - include their artifacts and contents
	if (project.specs && Object.keys(project.specs).length > 0) {
		for (const [specName, specData] of Object.entries(project.specs as Record<string, any>)) {
			const info = infoData?.specs?.[specName];
			const infoText = info ? buildTooltip(info.doc, info.link) : null;
			const specChildren: TreeNode[] = [];

			// Spec artifacts
			if (specData._artifacts && Object.keys(specData._artifacts).length > 0) {
				for (const [artifactType, artifactData] of Object.entries(specData._artifacts)) {
					const artInfo = infoData?.artifact?.[artifactType];
					const artInfoText = artInfo ? buildTooltip(artInfo.doc, artInfo.link) : null;

					if (typeof artifactData === 'string') {
						specChildren.push({
							key: artifactType,
							infoData: artInfoText,
							projectUrl,
							itemType: 'artifact',
							qname: `${specName}.${artifactType}`
						});
					} else if (artifactData && typeof artifactData === 'object') {
						for (const [name, _] of Object.entries(artifactData as Record<string, any>)) {
							specChildren.push({
								key: `${artifactType}.${name}`,
								infoData: artInfoText,
								projectUrl,
								itemType: 'artifact',
								qname: `${specName}.${artifactType}.${name}`
							});
						}
					}
				}
			}

			// Spec contents (optional, user didn't explicitly ask to list them but implied "listed" for specs)
			// User said: "Each spec child of a project may also contain artifacts; I would like these to be listed,
			// and the "Make" button also applied to them. "spec' and "contents" items should not get this button."
			// This suggests only artifacts of specs should be listed.

			projectChildren.push({
				key: specName,
				infoData: infoText,
				projectUrl,
				itemType: 'spec',
				children: specChildren.length > 0 ? specChildren : undefined
			});
		}
	}

	return projectChildren;
}

function getExampleData(): TreeNode {
	try {
		const out = execSync("projspec library list --json-out", { stdio: 'pipe', encoding: 'utf-8' });
		cachedLibraryData = JSON.parse(out) as Record<string, any>;

		const children: TreeNode[] = [];

		// Data is a dict of project_url -> project_data
		for (const [projectUrl, project] of Object.entries(cachedLibraryData)) {
			const projectChildren = buildTreeNodes(projectUrl, project);

			// Extract basename from project URL for display
			const projectBasename = projectUrl.split('/').pop() || projectUrl;
			children.push({
				key: `${projectBasename} (${projectUrl})`,
				infoData: projectUrl,
				children: projectChildren,
				data: project,
				isProject: true
			});
		}

		return { key: "projects", children };
	} catch (error) {
		return {
			key: "projects",
			children: []
		};
	}
}

async function handleOpenProject(item: TreeNode) {
	if (!item || !item.infoData || item.infoData.trim() === '') {
		return;
	}

	const projectUrl = item.infoData;

	// Only handle file:// URLs
	if (projectUrl.startsWith('file://')) {
		const fsPath = projectUrl.replace('file://', '');
		const uri = vscode.Uri.file(fsPath);
		await vscode.commands.executeCommand('vscode.openFolder', uri, { forceNewWindow: true });
	} else if (projectUrl.startsWith('gs://')) {
		vscode.window.showErrorMessage('Cannot open GCS buckets directly. Clone the repository locally first.');
	} else {
		vscode.window.showErrorMessage(`Unsupported project URL scheme: ${projectUrl}`);
	}
}

function handleMakeArtifact(item: TreeNode) {
	if (!item || !item.qname || !item.projectUrl) { return; }
	let projectPath = item.projectUrl;
	if (projectPath.startsWith('file://')) {
		projectPath = projectPath.replace('file://', '');
	}
	let terminal = vscode.window.terminals.find(t => t.name === 'projspec');
	if (!terminal) { terminal = vscode.window.createTerminal('projspec'); }
	terminal.show();
	terminal.sendText(`projspec make ${item.qname} "${projectPath}"`);
}

function handleSelectItem(item: TreeNode) {
	if (!item || !item.projectUrl) {
		return;
	}

	const data = cachedLibraryData;
	if (!data) {
		vscode.window.showErrorMessage('Project library data is not loaded yet.');
		return;
	}
	const projectData = data[item.projectUrl];
	if (!projectData) {
		vscode.window.showErrorMessage(`Project not found: ${item.projectUrl}`);
		return;
	}

	const projectBasename = item.projectUrl.split('/').pop() || item.projectUrl;

	if (detailsPanel) {
		detailsPanel.reveal(vscode.ViewColumn.Two, true);
		if (detailsPanelProjectUrl === item.projectUrl) {
			// Same project already shown — just scroll to the item
			detailsPanel.webview.postMessage({ command: 'scrollTo', key: item.key });
			return;
		}
	} else {
		detailsPanel = vscode.window.createWebviewPanel(
			'projspecDetails',
			`${projectBasename} — details`,
			{ viewColumn: vscode.ViewColumn.Two, preserveFocus: true },
			{ enableScripts: true, retainContextWhenHidden: true }
		);
		if (extensionLogoUri) { detailsPanel.iconPath = extensionLogoUri; }
		detailsPanel.onDidDispose(() => { detailsPanel = undefined; detailsPanelProjectUrl = undefined; });
		detailsPanel.webview.onDidReceiveMessage(message => {
			if (message.command === 'makeArtifact') { handleMakeArtifact(message.item); }
		});
	}

	detailsPanelProjectUrl = item.projectUrl;
	detailsPanel.title = `${projectBasename} — details`;
	detailsPanel.webview.html = getDetailsWebviewContent(projectBasename, item.projectUrl, projectData, item.key);
}

export function activate(context: vscode.ExtensionContext) {
	extensionLogoUri = vscode.Uri.joinPath(context.extensionUri, 'logo.png');

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showTree', async () => {
		const treeData = getExampleData();
		const infoData = getInfoData();
		const specNames = infoData ? Object.keys(infoData.specs) : [];

		// Create a webview panel for the tree
		const panel = vscode.window.createWebviewPanel(
			'projspecTree',
			'Project Library',
			vscode.ViewColumn.One,
			{
				enableScripts: true,
				retainContextWhenHidden: true
			}
		);

		if (extensionLogoUri) { panel.iconPath = extensionLogoUri; }

		// Set the HTML content for the webview
		panel.webview.html = getTreeWebviewContent(treeData, specNames);

		// Handle messages from the webview
		panel.webview.onDidReceiveMessage(
			async message => {
				switch (message.command) {
					case 'scan':
						if (vscode.workspace.workspaceFolders !== undefined) {
							const folderPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
							try {
								execSync(`projspec scan --library ${folderPath}`, { stdio: 'pipe', encoding: 'utf-8' });

								// Re-fetch data
								const treeData = getExampleData();
								const infoData = getInfoData();
								const specNames = infoData ? Object.keys(infoData.specs) : [];
								// Update webview
								panel.webview.html = getTreeWebviewContent(treeData, specNames, `file://${folderPath}`);
							} catch (error) {
								vscode.window.showErrorMessage(`Scan failed: ${error}`);
							}
						}
						break;
				case 'openProject':
					await handleOpenProject(message.item);
					break;
				case 'removeProject':
					if (message.item && message.item.infoData) {
						try {
							execSync(`projspec library delete ${message.item.infoData}`, { stdio: 'pipe', encoding: 'utf-8' });
							const treeData = getExampleData();
							const infoData = getInfoData();
							const specNames = infoData ? Object.keys(infoData.specs) : [];
							panel.webview.html = getTreeWebviewContent(treeData, specNames);
						} catch (error) {
							vscode.window.showErrorMessage(`Remove failed: ${error}`);
						}
					}
					break;
				case 'selectItem':
					handleSelectItem(message.item);
					break;
					case 'createProject':
						if (vscode.workspace.workspaceFolders !== undefined) {
							const folderPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
							try {
								const out = execSync(`projspec create ${message.projectType} ${folderPath}`, { stdio: 'pipe', encoding: 'utf-8' });
								const files = out.split('\n').map((f: string) => f.trim()).filter((f: string) => f.length > 0);

								for (const file of files) {
									const filePath = vscode.Uri.file(file);
									const doc = await vscode.workspace.openTextDocument(filePath);
									await vscode.window.showTextDocument(doc, { preview: false });
								}

								// Scan the new project into the library
								execSync(`projspec scan --library ${folderPath}`, { stdio: 'pipe', encoding: 'utf-8' });

								// Re-fetch data and refresh the tree
								const treeData = getExampleData();
								const infoData = getInfoData();
								const specNames = infoData ? Object.keys(infoData.specs) : [];
								panel.webview.html = getTreeWebviewContent(treeData, specNames);
							} catch (error) {
								vscode.window.showErrorMessage(`Create project failed: ${error}`);
							}
						}
					break;
				case 'makeArtifact':
					handleMakeArtifact(message.item);
					break;
				}
			},
			undefined,
			context.subscriptions
		);
	}));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showJson', async (item: TreeNode) => {
		if (!item || !item.key) {
			return;
		}

		const jsonContent = JSON.stringify(item.data || {}, null, 2);
		const doc = await vscode.workspace.openTextDocument({
			language: 'json',
			content: jsonContent
		});
		await vscode.window.showTextDocument(doc, { preview: false });
	}));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showInfo', async (...args: any[]) => {

		let item: TreeNode | undefined;

		// Try different ways VS Code might pass the tree item data
		if (args.length > 0) {
			// First argument might be the tree item
			item = args[0] as TreeNode;
		}

		if (!item || typeof item !== 'object') {
			vscode.window.showErrorMessage('No valid item provided to showInfo command');
			return;
		}

		let infoContent = '';
		if (item.infoData && item.infoData.trim() !== '') {
			infoContent = item.infoData;
		} else {
			// Show a message that info is not available for this specific item
			infoContent = `Information for ${item.itemType || 'item'} type "${item.key}" is not currently available.`;
		}

		// Create a webview panel for the information popup
		const panel = vscode.window.createWebviewPanel(
			'projspecInfo',
			`Info: ${item.key}`,
			vscode.ViewColumn.Beside,
			{
				enableScripts: true,
				retainContextWhenHidden: false
			}
		);

		// Set the HTML content for the webview
		panel.webview.html = getInfoWebviewContent(item.key, infoContent);
	}));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showItem', (item: TreeNode) => {
		handleSelectItem(item);
	}));
}

function getDetailsWebviewContent(projectBasename: string, projectUrl: string, project: any, highlightKey?: string): string {
	const infoData = getInfoData();

	// Keys that are internal implementation details and add no user-facing value
	const SKIP_KEYS = new Set(['klass', 'proc', 'storage_options', 'children', 'url']);

	// Classify what type of colour-coding a node should get based on where it sits in the tree
	type NodeRole = 'spec' | 'content' | 'artifact' | 'field' | 'none';

	interface DetailNode {
		label: string;       // display text
		value?: string;      // inline scalar value, shown after a colon
		role: NodeRole;
		children?: DetailNode[];
		// For artifact Make buttons:
		qname?: string;
		projectUrl?: string;
		// For info popups:
		infoData?: string | null;
		itemType?: string;
	}

	function escapeHtml(s: string): string {
		return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}

	// Render a scalar value compactly
	function scalarLabel(v: any): string {
		if (v === null || v === undefined) { return 'null'; }
		return String(v);
	}

	// Build detail nodes recursively.
	// role: the role inherited from the parent context
	// qnamePath: dot-separated path for artifact make commands (e.g. "pixi._artifacts.conda_env.default")
	function buildNodes(obj: any, role: NodeRole, qnamePath: string): DetailNode[] {
		if (obj === null || obj === undefined) { return []; }

		// Array of scalars → render as a single multi-value leaf
		if (Array.isArray(obj)) {
			return obj.map((item, i) => {
				if (item !== null && typeof item === 'object') {
					return { label: String(i), role, children: buildNodes(item, role, `${qnamePath}.${i}`) };
				}
				return { label: scalarLabel(item), role: 'field' };
			});
		}

		if (typeof obj !== 'object') {
			return [{ label: scalarLabel(obj), role: 'field' }];
		}

		const nodes: DetailNode[] = [];

		for (const [key, value] of Object.entries(obj)) {
			if (SKIP_KEYS.has(key)) { continue; }

			const childPath = qnamePath ? `${qnamePath}.${key}` : key;

			// Determine child role based on structural key names
			let childRole: NodeRole = role;
			if (key === 'specs' || key === '_contents' || key === 'contents' || key === '_artifacts' || key === 'artifacts') {
				// These are container keys — their children take a specific role.
				// Pass qnamePath (not childPath) so the container key itself is NOT
				// included in the qname used by `projspec make`.
				childRole = key === 'specs' ? 'spec'
					: (key === '_contents' || key === 'contents') ? 'content'
					: 'artifact';
				// Don't emit a wrapper node for these containers, just inline their children with the right role
				const children = buildNodes(value, childRole, qnamePath);
				nodes.push(...children);
				continue;
			}

				// ── Artifact special handling ──────────────────────────────────
			// Artifacts in the serialised JSON take one of two shapes:
			//   1. string leaf:  { "launch": "<cmd>, <state>" }
			//   2. named dict:   { "conda_env": { "default": "<cmd>, <state>", "another": "..." } }
			// In both cases the "leaf" artifact nodes must carry a qname so
			// the Make button can invoke `projspec make <qname> "<path>"`.
			if (role === 'artifact') {
				// Attach info popup data for this artifact type
				let artInfoData: string | null = null;
				const artInfo = infoData?.artifact?.[key];
				if (artInfo) { artInfoData = buildTooltip(artInfo.doc, artInfo.link); }

				if (typeof value === 'string' || value === null) {
					// Shape 1: single string artifact — childPath is the qname
					nodes.push({
						label: key,
						role: 'artifact',
						qname: childPath,
						projectUrl,
						infoData: artInfoData,
						itemType: 'artifact',
					});
				} else if (value && typeof value === 'object' && !Array.isArray(value)) {
					// Inspect the values: if they are all strings/null this is shape 2
					// (named artifacts); otherwise it's an artifact object with fields.
					const entries = Object.entries(value as Record<string, any>);
					const allStrings = entries.every(([, v]) => typeof v === 'string' || v === null);
					if (allStrings) {
						// Shape 2: named artifacts — emit one node per name
						const namedChildren: DetailNode[] = entries.map(([name, cmd]) => ({
							label: name,
							role: 'artifact' as NodeRole,
							qname: `${childPath}.${name}`,
							projectUrl,
							itemType: 'artifact',
						}));
						nodes.push({
							label: key,
							role: 'artifact',
							children: namedChildren.length > 0 ? namedChildren : undefined,
							infoData: artInfoData,
							itemType: 'artifact',
						});
					} else {
						// Artifact object with fields (unusual) — recurse normally,
						// treating the whole object as one artifact leaf.
						const children = buildNodes(value, 'field', childPath);
						nodes.push({
							label: key,
							role: 'artifact',
							qname: childPath,
							projectUrl,
							children: children.length > 0 ? children : undefined,
							infoData: artInfoData,
							itemType: 'artifact',
						});
					}
				}
				continue;
			}

			// Scalar value → leaf with inline display
			if (value === null || typeof value !== 'object' || Array.isArray(value)) {
				if (Array.isArray(value) && value.every(v => v === null || typeof v !== 'object')) {
					// Array of scalars: show as expandable list
					const arrayChildren: DetailNode[] = (value as any[]).map(v => ({ label: scalarLabel(v), role: 'field' as NodeRole }));
					nodes.push({ label: key, role: role === 'content' ? 'content' : role === 'spec' ? 'spec' : 'field', children: arrayChildren.length > 0 ? arrayChildren : undefined });
				} else if (Array.isArray(value)) {
					nodes.push({ label: key, role, children: buildNodes(value, role, childPath) });
				} else {
					nodes.push({ label: key, value: scalarLabel(value), role: role === 'content' ? 'content' : role === 'spec' ? 'spec' : 'field' });
				}
				continue;
			}

			// Object value
			const children = buildNodes(value, role, childPath);

			// (qname is only relevant for artifacts, handled above)

			// Attach info popup data based on role
			let nodeInfoData: string | null = null;
			if (role === 'spec') {
				const info = infoData?.specs?.[key];
				if (info) { nodeInfoData = buildTooltip(info.doc, info.link); }
			} else if (role === 'content') {
				const info = infoData?.content?.[key];
				if (info) { nodeInfoData = buildTooltip(info.doc, info.link); }
			}

			nodes.push({
				label: key,
				role,
				children: children.length > 0 ? children : undefined,
				infoData: nodeInfoData,
				itemType: role !== 'none' && role !== 'field' ? role : undefined,
			});
		}

		return nodes;
	}

	const detailNodes = buildNodes(project, 'none', '');

	// Determine if a node is an artifact that can be "made":
	// it must have a qname and no children that are themselves artifacts
	function isLeafArtifact(node: DetailNode): boolean {
		if (node.role !== 'artifact' || !node.qname) { return false; }
		if (!node.children) { return true; }
		return !node.children.some(c => c.role === 'artifact');
	}

	function renderDetailNode(node: DetailNode, depth: number): string {
		const hasChildren = node.children && node.children.length > 0;
		const canMake = isLeafArtifact(node);
		const hasInfoPopup = node.infoData != null && node.role !== 'field' && node.role !== 'none';

		let nodeClass = 'tree-node';
		if (node.role === 'spec') { nodeClass += ' spec-node'; }
		else if (node.role === 'content') { nodeClass += ' content-node'; }
		else if (node.role === 'artifact') { nodeClass += ' artifact-node'; }
		else if (node.role === 'field') { nodeClass += ' field-node'; }

		const iconClass = hasChildren
			? 'tree-icon expandable'
			: 'tree-icon leaf';

		// Build data attribute for Make / info buttons
		const nodeData = JSON.stringify({
			key: node.label,
			qname: node.qname,
			projectUrl: node.projectUrl,
			itemType: node.itemType,
			infoData: node.infoData,
		}).replace(/"/g, '&quot;');

		const labelText = node.value !== undefined
			? `${escapeHtml(node.label)}: <span class="field-value">${escapeHtml(node.value)}</span>`
			: escapeHtml(node.label);

		const childrenHtml = hasChildren
			? `<ul class="tree-children" data-depth="${depth + 1}">${node.children!.map(c => renderDetailNode(c, depth + 1)).join('')}</ul>`
			: '';

		return `<li class="tree-item">
			<div class="${nodeClass}" data-item="${nodeData}">
				<span class="${iconClass}"></span>
				<span class="tree-label">${labelText}</span>
				${canMake ? `<button class="make-button" data-item="${nodeData}" title="Make artifact">Make</button>` : ''}
				${hasInfoPopup ? `<button class="info-button" data-item="${nodeData}" title="Show information">i</button>` : ''}
			</div>
			${childrenHtml}
		</li>`;
	}

	const treeHtml = detailNodes.map(n => renderDetailNode(n, 0)).join('');

	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(projectBasename)} — details</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }

        .project-header {
            padding: 8px 10px;
            border-bottom: 1px solid var(--vscode-panel-border);
            flex-shrink: 0;
        }

        .project-title {
            font-weight: bold;
            font-size: 14px;
            color: var(--vscode-symbolIcon-folderForeground);
            margin-bottom: 2px;
        }

        .project-url {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            word-break: break-all;
        }

        .tree { list-style: none; margin: 0; padding: 0; }
        .tree-item { margin: 0; padding: 0; }

        #tree-container {
            flex: 1;
            overflow-y: auto;
            padding: 6px 10px;
        }

        .tree-node {
            display: flex;
            align-items: center;
            padding: 3px 8px;
            cursor: default;
            border-radius: 4px;
            transition: background-color 0.1s ease;
        }

        .tree-node:hover { background-color: var(--vscode-list-hoverBackground); }

        .tree-node.selected {
            background-color: var(--vscode-list-activeSelectionBackground);
            color: var(--vscode-list-activeSelectionForeground);
        }

        .tree-icon {
            width: 16px; height: 16px; margin-right: 4px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; flex-shrink: 0;
        }

        .tree-icon.expandable::before { content: "▶"; font-size: 10px; transition: transform 0.1s ease; }
        .tree-icon.expanded::before { transform: rotate(90deg); }
        .tree-icon.leaf::before {
            content: ""; width: 6px; height: 6px;
            background: var(--vscode-symbolIcon-fileBackground); border-radius: 50%;
            display: block;
        }

        .tree-label { flex: 1; padding: 2px 4px; }

        .field-value {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
        }

        .tree-children { list-style: none; margin: 0; padding-left: 20px; display: none; }
        .tree-children.expanded { display: block; }

        .spec-node { color: var(--vscode-symbolIcon-functionForeground); }
        .content-node { color: #4ec9b0; }
        .artifact-node { color: #ce9178; }
        .field-node { color: var(--vscode-foreground); }

        .info-button {
            width: 20px; height: 20px; border-radius: 50%;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-size: 12px; font-weight: bold; margin-left: 8px;
            opacity: 0.7; transition: all 0.2s ease;
        }
        .info-button:hover { opacity: 1; background: var(--vscode-button-hoverBackground); transform: scale(1.1); }

        .make-button {
            padding: 2px 8px;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: 1px solid var(--vscode-button-border);
            border-radius: 2px; cursor: pointer;
            font-size: 10px; font-family: inherit; margin-left: 8px;
            opacity: 0.8; transition: all 0.2s ease;
        }
        .make-button:hover { opacity: 1; background-color: var(--vscode-button-hoverBackground); }

        /* Info popup */
        .info-popup {
            position: absolute;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            padding: 16px; max-width: 400px; min-width: 250px;
            z-index: 1000; font-size: var(--vscode-font-size); line-height: 1.5;
            display: none;
        }
        .info-popup.visible { display: block; }
        .popup-header { display: flex; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--vscode-panel-border); }
        .popup-icon { width: 20px; height: 20px; margin-right: 8px; border-radius: 50%; background-color: var(--vscode-button-background); color: var(--vscode-button-foreground); display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; }
        .popup-title { font-weight: bold; margin: 0; color: var(--vscode-foreground); }
        .popup-content { margin-bottom: 8px; }
        .popup-section { margin-bottom: 12px; }
        .popup-section:last-child { margin-bottom: 0; }
        .section-title { font-weight: bold; margin-bottom: 4px; color: var(--vscode-descriptionForeground); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
        .section-content { white-space: pre-wrap; word-wrap: break-word; }
        .popup-link { color: var(--vscode-textLink-foreground); text-decoration: none; word-break: break-all; }
        .popup-link:hover { text-decoration: underline; }
        .no-info { color: var(--vscode-descriptionForeground); font-style: italic; }
        .info-popup::before { content: ""; position: absolute; top: -8px; left: 20px; width: 0; height: 0; border-left: 8px solid transparent; border-right: 8px solid transparent; border-bottom: 8px solid var(--vscode-panel-border); }
        .info-popup::after { content: ""; position: absolute; top: -7px; left: 21px; width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-bottom: 7px solid var(--vscode-editor-background); }

        .controls-container {
            padding: 6px 8px;
            display: flex;
            gap: 6px;
            border-bottom: 1px solid var(--vscode-panel-border);
            flex-shrink: 0;
        }

        .control-button {
            padding: 2px 8px;
            background-color: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
            border: 1px solid var(--vscode-button-border);
            border-radius: 2px;
            cursor: pointer;
            font-size: 11px;
            font-family: inherit;
        }

        .control-button:hover { background-color: var(--vscode-button-secondaryHoverBackground); }
        .control-button.active {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }
    </style>
</head>
<body>
    <div class="project-header">
        <div class="project-title">${escapeHtml(projectBasename)}</div>
        <div class="project-url">${escapeHtml(projectUrl)}</div>
    </div>

    <div class="controls-container">
        <button id="btn-default" class="control-button active">Default view</button>
        <button id="btn-expand" class="control-button">Expand All</button>
        <button id="btn-collapse" class="control-button">Collapse All</button>
    </div>

    <div id="tree-container">
        <ul class="tree">${treeHtml}</ul>
    </div>

    <!-- Info Popup -->
    <div id="info-popup" class="info-popup">
        <div class="popup-header">
            <div class="popup-icon">i</div>
            <h3 class="popup-title" id="popup-title"></h3>
        </div>
        <div class="popup-content" id="popup-content"></div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const popup = document.getElementById('info-popup');
        const popupTitle = document.getElementById('popup-title');
        const popupContent = document.getElementById('popup-content');

        // ── Expand / collapse helpers ──────────────────────────────────────

        function setExpanded(ul, expanded) {
            ul.classList.toggle('expanded', expanded);
            const icon = ul.closest('.tree-item')?.querySelector(':scope > .tree-node > .tree-icon.expandable');
            if (icon) { icon.classList.toggle('expanded', expanded); }
        }

        function expandAll() {
            document.querySelectorAll('.tree-children').forEach(ul => setExpanded(ul, true));
        }

        function collapseAll() {
            document.querySelectorAll('.tree-children').forEach(ul => setExpanded(ul, false));
        }

        // Expand depth 1 (data-depth="1"), collapse depth >= 2
        function defaultView() {
            document.querySelectorAll('.tree-children').forEach(ul => {
                const depth = parseInt(ul.dataset.depth || '1', 10);
                setExpanded(ul, depth <= 1);
            });
        }

        function setActiveButton(btn) {
            document.querySelectorAll('.control-button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }

        document.getElementById('btn-expand').addEventListener('click', (e) => {
            expandAll();
            setActiveButton(e.target);
        });
        document.getElementById('btn-collapse').addEventListener('click', (e) => {
            collapseAll();
            setActiveButton(e.target);
        });
        document.getElementById('btn-default').addEventListener('click', (e) => {
            defaultView();
            setActiveButton(e.target);
        });

        // ── Find and highlight a node by a dot-separated key path ──────────

        function scrollToKey(key) {
            const segments = key.split('.');
            let searchRoot = document.querySelector('.tree');
            let targetNode = null;

            for (let i = 0; i < segments.length; i++) {
                const seg = segments[i];
                if (!searchRoot) { break; }
                const candidates = searchRoot.querySelectorAll(':scope > .tree-item > .tree-node');
                let found = null;
                for (const node of candidates) {
                    try {
                        const data = JSON.parse(node.dataset.item || '{}');
                        if (data.key === seg) { found = node; break; }
                    } catch (e) {}
                }
                if (!found) { break; }
                targetNode = found;
                // Ensure this node's children list is expanded so we can descend
                const treeItem = found.closest('.tree-item');
                const childList = treeItem ? treeItem.querySelector(':scope > .tree-children') : null;
                if (childList) { setExpanded(childList, true); }
                searchRoot = childList;
            }

            if (targetNode) {
                document.querySelectorAll('.tree-node.selected').forEach(n => n.classList.remove('selected'));
                targetNode.classList.add('selected');
                targetNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        // ── Initialise ─────────────────────────────────────────────────────

        const initialKey = ${highlightKey ? JSON.stringify(highlightKey) : 'null'};
        window.addEventListener('DOMContentLoaded', () => {
            defaultView();
            if (initialKey) { scrollToKey(initialKey); }
        });

        // Handle messages from the extension (scrollTo when panel is reused)
        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'scrollTo') { scrollToKey(message.key); }
        });

        // ── Tree interaction ───────────────────────────────────────────────

        document.addEventListener('click', (e) => {
            // Expand/collapse arrow
            if (e.target.classList.contains('tree-icon') && e.target.classList.contains('expandable')) {
                const treeItem = e.target.closest('.tree-item');
                const children = treeItem.querySelector(':scope > .tree-children');
                setExpanded(children, !children.classList.contains('expanded'));
                return;
            }

            // Info button
            if (e.target.classList.contains('info-button')) {
                e.stopPropagation();
                showInfoPopup(e.target, JSON.parse(e.target.dataset.item));
                return;
            }

            // Make button
            if (e.target.classList.contains('make-button')) {
                e.stopPropagation();
                vscode.postMessage({ command: 'makeArtifact', item: JSON.parse(e.target.dataset.item) });
                return;
            }

            // Close popup when clicking elsewhere
            if (!popup.contains(e.target) && !e.target.classList.contains('info-button')) {
                hideInfoPopup();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { hideInfoPopup(); }
        });

        // ── Info popup ─────────────────────────────────────────────────────

        function showInfoPopup(button, itemData) {
            const rect = button.getBoundingClientRect();
            const container = document.getElementById('tree-container');
            const containerRect = container.getBoundingClientRect();
            popup.style.left = (rect.right - containerRect.left + 10) + 'px';
            popup.style.top = (rect.top - containerRect.top - 10) + 'px';
            popupTitle.textContent = itemData.key;

            let contentHtml = '';
            if (itemData.infoData && itemData.infoData.trim() !== '') {
                let doc = "", link = "";
                try {
                    const info = JSON.parse(itemData.infoData);
                    doc = info.doc || ""; link = info.link || "";
                } catch (e) {
                    const parts = itemData.infoData.split('\\n\\n');
                    doc = parts[0] || ''; link = parts[1] || '';
                }
                const docParts = doc.split('\\n').map(p => p.trim()).filter(p => p.length > 0);
                const summary = docParts.length > 0 ? docParts[0] : "";
                const extra = docParts.slice(1);
                if (summary) { contentHtml += '<div class="popup-section"><div class="section-content" style="font-weight:bold;margin-bottom:8px;">' + summary + '</div></div>'; }
                if (extra.length > 0) { contentHtml += '<div class="popup-section"><div class="section-content">' + extra.map(p => '<p style="margin-top:0;margin-bottom:8px;">' + p + '</p>').join('') + '</div></div>'; }
                if (link) { contentHtml += '<div class="popup-section"><div class="section-title">More Information</div><div class="section-content"><a href="' + link + '" class="popup-link" target="_blank">' + link + '</a></div></div>'; }
            }
            if (!contentHtml) {
                contentHtml = '<div class="no-info">Information for ' + (itemData.itemType || 'item') + ' type "' + itemData.key + '" is not currently available.</div>';
            }
            popupContent.innerHTML = contentHtml;
            popup.classList.add('visible');

            const popupRect = popup.getBoundingClientRect();
            if (popupRect.right > window.innerWidth) { popup.style.left = (rect.left - containerRect.left - popupRect.width - 10) + 'px'; }
            if (popupRect.bottom > window.innerHeight) { popup.style.top = (rect.bottom - containerRect.top - popupRect.height + 10) + 'px'; }
        }

        function hideInfoPopup() { popup.classList.remove('visible'); }
    </script>
</body>
</html>`;
}

function getTreeWebviewContent(treeData: TreeNode, specNames: string[] = [], scrollToProjectUrl?: string): string {
	const specOptions = specNames.map(spec => `<option value="${spec}">${spec}</option>`).join('');
	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Library</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            margin: 0;
            padding: 10px;
            position: relative;
        }

        .tree {
            list-style: none;
            margin: 0;
            padding: 0;
        }

        .tree-item {
            margin: 0;
            padding: 0;
        }

        .tree-node {
            display: flex;
            align-items: center;
            padding: 4px 8px;
            cursor: pointer;
            border-radius: 4px;
            transition: background-color 0.1s ease;
        }

        .tree-node:hover {
            background-color: var(--vscode-list-hoverBackground);
        }

        .tree-node.selected {
            background-color: var(--vscode-list-activeSelectionBackground);
            color: var(--vscode-list-activeSelectionForeground);
        }

        .tree-icon {
            width: 16px;
            height: 16px;
            margin-right: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }

        .tree-icon.expandable::before {
            content: "▶";
            font-size: 10px;
            transition: transform 0.1s ease;
        }

        .tree-icon.expanded::before {
            transform: rotate(90deg);
        }

        .tree-icon.leaf::before {
            content: "";
            width: 6px;
            height: 6px;
            background: var(--vscode-symbolIcon-fileBackground);
            border-radius: 50%;
        }

        .tree-label {
            flex: 1;
            padding: 2px 4px;
        }

        .info-button {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            margin-left: 8px;
            transition: all 0.2s ease;
            opacity: 0.7;
            position: relative;
        }

        .info-button:hover {
            opacity: 1;
            background: var(--vscode-button-hoverBackground);
            transform: scale(1.1);
        }

        .make-button {
            padding: 2px 8px;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: 1px solid var(--vscode-button-border);
            border-radius: 2px;
            cursor: pointer;
            font-size: 10px;
            font-family: inherit;
            margin-left: 8px;
            opacity: 0.8;
            transition: all 0.2s ease;
        }

        .make-button:hover {
            opacity: 1;
            background-color: var(--vscode-button-hoverBackground);
        }

        .tree-children {
            list-style: none;
            margin: 0;
            padding-left: 20px;
            display: none;
        }

        .tree-children.expanded {
            display: block;
        }

        .project-node {
            font-weight: bold;
            color: var(--vscode-symbolIcon-folderForeground);
        }

        .content-node {
            color: #4ec9b0; /* green */
        }

        .artifact-node {
            color: #ce9178; /* yellow/orange */
        }

        .spec-node {
            color: var(--vscode-symbolIcon-functionForeground);
        }

        .folder-node {
            color: var(--vscode-symbolIcon-folderForeground);
            font-weight: 500;
        }

        /* Popup Styles */
        .info-popup {
            position: absolute;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            padding: 16px;
            max-width: 400px;
            min-width: 250px;
            z-index: 1000;
            font-size: var(--vscode-font-size);
            line-height: 1.5;
            display: none;
        }

        .info-popup.visible {
            display: block;
        }

        .popup-header {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }

        .popup-icon {
            width: 20px;
            height: 20px;
            margin-right: 8px;
            border-radius: 50%;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
        }

        .popup-title {
            font-weight: bold;
            margin: 0;
            color: var(--vscode-foreground);
        }

        .popup-content {
            margin-bottom: 8px;
        }

        .popup-section {
            margin-bottom: 12px;
        }

        .popup-section:last-child {
            margin-bottom: 0;
        }

        .section-title {
            font-weight: bold;
            margin-bottom: 4px;
            color: var(--vscode-descriptionForeground);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .section-content {
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .popup-link {
            color: var(--vscode-textLink-foreground);
            text-decoration: none;
            word-break: break-all;
        }

        .popup-link:hover {
            text-decoration: underline;
        }

        .no-info {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
        }

        /* Search Styles */
        .search-container {
            padding: 8px;
            position: sticky;
            top: 0;
            background-color: var(--vscode-editor-background);
            z-index: 10;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 8px;
        }

        .search-input-wrapper {
            position: relative;
            display: flex;
            align-items: center;
        }

        #search-input {
            width: 100%;
            padding: 4px 24px 4px 8px;
            box-sizing: border-box;
            background-color: var(--vscode-settings-textInputBackground);
            color: var(--vscode-settings-textInputForeground);
            border: 1px solid var(--vscode-settings-textInputBorder);
            border-radius: 2px;
            font-family: inherit;
            font-size: inherit;
        }

        #search-input:focus {
            outline: 1px solid var(--vscode-focusBorder);
            border-color: var(--vscode-focusBorder);
        }

        #search-clear {
            position: absolute;
            right: 4px;
            background: none;
            border: none;
            padding: 0 2px;
            cursor: pointer;
            color: var(--vscode-settings-textInputForeground);
            opacity: 0.6;
            font-size: 14px;
            line-height: 1;
            display: none;
        }

        #search-clear:hover {
            opacity: 1;
        }

        /* Button Styles */
        .controls-top-container {
            padding: 8px;
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 8px;
        }

        .controls-bottom-container {
            padding: 8px;
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 8px;
        }

        .control-button {
            padding: 2px 8px;
            background-color: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
            border: 1px solid var(--vscode-button-border);
            border-radius: 2px;
            cursor: pointer;
            font-size: 11px;
            font-family: inherit;
        }

        .control-button:hover {
            background-color: var(--vscode-button-secondaryHoverBackground);
        }

        .control-button:focus {
            outline: 1px solid var(--vscode-focusBorder);
        }

        /* Popup arrow */
        .info-popup::before {
            content: "";
            position: absolute;
            top: -8px;
            left: 20px;
            width: 0;
            height: 0;
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-bottom: 8px solid var(--vscode-panel-border);
        }

        .info-popup::after {
            content: "";
            position: absolute;
            top: -7px;
            left: 21px;
            width: 0;
            height: 0;
            border-left: 7px solid transparent;
            border-right: 7px solid transparent;
            border-bottom: 7px solid var(--vscode-editor-background);
        }

        /* Modal dialog styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 2000;
        }

        .modal-overlay.visible {
            display: flex;
        }

        .modal-dialog {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
            padding: 20px;
            width: 350px;
            max-width: 90%;
        }

        .modal-title {
            margin-top: 0;
            margin-bottom: 16px;
            font-size: 16px;
            font-weight: bold;
            color: var(--vscode-foreground);
        }

        .modal-content {
            margin-bottom: 20px;
        }

        .modal-label {
            display: block;
            margin-bottom: 8px;
            color: var(--vscode-foreground);
        }

        .modal-select, .modal-input {
            width: 100%;
            padding: 6px;
            background: var(--vscode-settings-textInputBackground);
            color: var(--vscode-settings-textInputForeground);
            border: 1px solid var(--vscode-settings-textInputBorder);
            border-radius: 2px;
            font-family: inherit;
            box-sizing: border-box;
        }

        .autocomplete-container {
            position: relative;
            width: 100%;
        }

        .autocomplete-suggestions {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-top: none;
            max-height: 150px;
            overflow-y: auto;
            z-index: 2100;
            display: none;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }

        .autocomplete-suggestions.visible {
            display: block;
        }

        .suggestion-item {
            padding: 6px 10px;
            cursor: pointer;
            transition: background-color 0.1s ease;
        }

        .suggestion-item:hover, .suggestion-item.active {
            background-color: var(--vscode-list-hoverBackground);
        }

        .modal-buttons {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }

        .modal-button {
            padding: 6px 16px;
            border-radius: 2px;
            border: 1px solid var(--vscode-button-border);
            cursor: pointer;
            font-family: inherit;
            font-size: 13px;
        }

        .modal-button-primary {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }

        .modal-button-primary:hover {
            background: var(--vscode-button-hoverBackground);
        }

        .modal-button-secondary {
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
        }

        .modal-button-secondary:hover {
            background: var(--vscode-button-secondaryHoverBackground);
        }

        /* Context menu styles */
        .context-menu {
            position: fixed;
            background: var(--vscode-menu-background);
            border: 1px solid var(--vscode-menu-border);
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
            padding: 4px 0;
            z-index: 3000;
            display: none;
            min-width: 140px;
        }

        .context-menu.visible {
            display: block;
        }

        .context-menu-item {
            padding: 6px 16px;
            cursor: pointer;
            color: var(--vscode-menu-foreground);
            font-family: inherit;
            font-size: var(--vscode-font-size);
            white-space: nowrap;
        }

        .context-menu-item:hover {
            background: var(--vscode-menu-selectionBackground);
            color: var(--vscode-menu-selectionForeground);
        }

        /* Loading overlay */
        .loading-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.35);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 4000;
            cursor: wait;
        }

        .loading-overlay.visible {
            display: flex;
        }

        .loading-spinner {
            width: 28px;
            height: 28px;
            border: 3px solid var(--vscode-foreground);
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.7s linear infinite;
            opacity: 0.8;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="controls-top-container">
        <button id="scan-project" class="control-button">Scan</button>
        <button id="create-project" class="control-button">Create</button>
    </div>
    <div class="search-container">
        <div class="search-input-wrapper">
            <input type="text" id="search-input" placeholder="Search projects..." aria-label="Search projects">
            <button id="search-clear" title="Clear search" aria-label="Clear search">&#x2715;</button>
        </div>
    </div>
    <div class="controls-bottom-container">
        <button id="expand-all" class="control-button">Expand All</button>
        <button id="collapse-all" class="control-button">Collapse All</button>
    </div>
    <div id="tree-container">
        <ul class="tree">
            ${generateTreeHTML(treeData)}
        </ul>
    </div>

    <!-- Loading overlay -->
    <div id="loading-overlay" class="loading-overlay">
        <div class="loading-spinner"></div>
    </div>

    <!-- Info Popup -->
    <div id="info-popup" class="info-popup">
        <div class="popup-header">
            <div class="popup-icon">i</div>
            <h3 class="popup-title" id="popup-title"></h3>
        </div>
        <div class="popup-content" id="popup-content"></div>
    </div>

    <!-- Context Menu -->
    <div id="context-menu" class="context-menu">
        <div class="context-menu-item" id="context-open">Open</div>
        <div class="context-menu-item" id="context-remove">Remove</div>
    </div>

    <!-- Create Project Modal -->
    <div id="create-modal" class="modal-overlay">
        <div class="modal-dialog">
            <h3 class="modal-title">Create Project</h3>
            <div class="modal-content">
                <label for="project-type-input" class="modal-label">Project Type:</label>
                <div class="autocomplete-container">
                    <input type="text" id="project-type-input" class="modal-input" placeholder="Search or select type..." autocomplete="off">
                    <div id="autocomplete-suggestions" class="autocomplete-suggestions"></div>
                </div>
            </div>
            <div class="modal-buttons">
                <button id="modal-cancel" class="modal-button modal-button-secondary">Cancel</button>
                <button id="modal-create" class="modal-button modal-button-primary">Create</button>
            </div>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const popup = document.getElementById('info-popup');
        const popupTitle = document.getElementById('popup-title');
        const popupContent = document.getElementById('popup-content');
        const searchInput = document.getElementById('search-input');
        const searchClear = document.getElementById('search-clear');
        const createModal = document.getElementById('create-modal');
        const typeInput = document.getElementById('project-type-input');
        const suggestionsContainer = document.getElementById('autocomplete-suggestions');
        const modalCancelBtn = document.getElementById('modal-cancel');
        const modalCreateBtn = document.getElementById('modal-create');
        const expandAllBtn = document.getElementById('expand-all');
        const collapseAllBtn = document.getElementById('collapse-all');
        const scanProjectBtn = document.getElementById('scan-project');
        const createProjectBtn = document.getElementById('create-project');
        const contextMenu = document.getElementById('context-menu');
        const contextOpenBtn = document.getElementById('context-open');
        const contextRemoveBtn = document.getElementById('context-remove');

        let contextMenuItem = null;

        const specNames = ${JSON.stringify(specNames)};
        let activeSuggestionIndex = -1;

        const scrollToProjectUrl = ${scrollToProjectUrl ? `'${scrollToProjectUrl}'` : 'null'};

        function setLoading(active) {
            document.getElementById('loading-overlay').classList.toggle('visible', active);
        }

        if (scrollToProjectUrl) {
            window.addEventListener('DOMContentLoaded', () => {
                const projectNodes = document.querySelectorAll('.tree-node.project-node');
                for (const node of projectNodes) {
                    const itemData = JSON.parse(node.dataset.item || '{}');
                    if (itemData.infoData === scrollToProjectUrl) {
                        // Expand this project
                        const treeItem = node.closest('.tree-item');
                        const children = treeItem.querySelector('.tree-children');
                        const icon = treeItem.querySelector('.tree-icon');

                        if (children) {
                            children.classList.add('expanded');
                        }
                        if (icon) {
                            icon.classList.add('expanded');
                        }

                        // Select this node
                        node.classList.add('selected');

                        // Scroll into view
                        node.scrollIntoView({ behavior: 'smooth', block: 'center' });

                        break;
                    }
                }
            });
        }

        // Handle scan project
        scanProjectBtn.addEventListener('click', () => {
            setLoading(true);
            vscode.postMessage({
                command: 'scan'
            });
        });

        // Handle create project
        createProjectBtn.addEventListener('click', () => {
            createModal.classList.add('visible');
            typeInput.value = '';
            typeInput.focus();
            renderSuggestions('');
        });

        // Autocomplete logic
        typeInput.addEventListener('input', (e) => {
            renderSuggestions(e.target.value);
        });

        typeInput.addEventListener('keydown', (e) => {
            const suggestions = suggestionsContainer.querySelectorAll('.suggestion-item');
            if (e.key === 'ArrowDown') {
                activeSuggestionIndex = Math.min(activeSuggestionIndex + 1, suggestions.length - 1);
                updateActiveSuggestion(suggestions);
                e.preventDefault();
            } else if (e.key === 'ArrowUp') {
                activeSuggestionIndex = Math.max(activeSuggestionIndex - 1, -1);
                updateActiveSuggestion(suggestions);
                e.preventDefault();
            } else if (e.key === 'Enter') {
                if (activeSuggestionIndex >= 0) {
                    selectSuggestion(suggestions[activeSuggestionIndex].textContent);
                    e.preventDefault();
                }
            }
        });

        function renderSuggestions(filter) {
            const filteredSpecs = specNames.filter(s => s.toLowerCase().includes(filter.toLowerCase()));
            suggestionsContainer.innerHTML = '';
            activeSuggestionIndex = -1;

            if (filteredSpecs.length > 0) {
                filteredSpecs.forEach(spec => {
                    const item = document.createElement('div');
                    item.className = 'suggestion-item';
                    item.textContent = spec;
                    item.addEventListener('click', () => selectSuggestion(spec));
                    suggestionsContainer.appendChild(item);
                });
                suggestionsContainer.classList.add('visible');
            } else {
                suggestionsContainer.classList.remove('visible');
            }
        }

        function updateActiveSuggestion(suggestions) {
            suggestions.forEach((s, i) => {
                if (i === activeSuggestionIndex) {
                    s.classList.add('active');
                    s.scrollIntoView({ block: 'nearest' });
                } else {
                    s.classList.remove('active');
                }
            });
        }

        function selectSuggestion(spec) {
            typeInput.value = spec;
            suggestionsContainer.classList.remove('visible');
            activeSuggestionIndex = -1;
        }

        // Close suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!typeInput.contains(e.target) && !suggestionsContainer.contains(e.target)) {
                suggestionsContainer.classList.remove('visible');
            }
        });

        // Handle search
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            searchClear.style.display = e.target.value ? 'block' : 'none';
            const projectNodes = document.querySelectorAll('.tree > .tree-item');

            projectNodes.forEach(projectItem => {
                // Find all labels within this project item (project name and child fields)
                const labels = projectItem.querySelectorAll('.tree-label');
                let found = false;

                for (const label of labels) {
                    if (label.textContent.toLowerCase().includes(searchTerm)) {
                        found = true;
                        break;
                    }
                }

                if (found) {
                    projectItem.style.display = '';
                } else {
                    projectItem.style.display = 'none';
                }
            });
        });

        // Handle search clear button
        searchClear.addEventListener('click', () => {
            searchInput.value = '';
            searchClear.style.display = 'none';
            document.querySelectorAll('.tree > .tree-item').forEach(projectItem => {
                projectItem.style.display = '';
            });
            searchInput.focus();
        });

        // Handle expand/collapse all
        expandAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.tree-children').forEach(children => {
                children.classList.add('expanded');
            });
            document.querySelectorAll('.tree-icon.expandable').forEach(icon => {
                icon.classList.add('expanded');
            });
        });

        collapseAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.tree-children').forEach(children => {
                children.classList.remove('expanded');
            });
            document.querySelectorAll('.tree-icon.expandable').forEach(icon => {
                icon.classList.remove('expanded');
            });
        });

        // Modal event listeners
        modalCancelBtn.addEventListener('click', () => {
            createModal.classList.remove('visible');
        });

        modalCreateBtn.addEventListener('click', () => {
            const projectType = typeInput.value;
            if (projectType) {
                vscode.postMessage({
                    command: 'createProject',
                    projectType: projectType
                });
                createModal.classList.remove('visible');
            } else {
                typeInput.focus();
            }
        });

        // Close modal on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                createModal.classList.remove('visible');
            }
        });

        // Handle tree expansion/collapse and clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('tree-icon') && e.target.classList.contains('expandable')) {
                const treeItem = e.target.closest('.tree-item');
                const children = treeItem.querySelector('.tree-children');
                const icon = e.target;

                if (children.classList.contains('expanded')) {
                    children.classList.remove('expanded');
                    icon.classList.remove('expanded');
                } else {
                    children.classList.add('expanded');
                    icon.classList.add('expanded');
                }
            }

            // Handle info button clicks
            if (e.target.classList.contains('info-button')) {
                e.stopPropagation();
                const itemData = JSON.parse(e.target.dataset.item);
                showInfoPopup(e.target, itemData);
                return;
            }

            // Handle make button clicks
            if (e.target.classList.contains('make-button')) {
                e.stopPropagation();
                const itemData = JSON.parse(e.target.dataset.item);
                vscode.postMessage({
                    command: 'makeArtifact',
                    item: itemData
                });
                return;
            }

            // Close popups if clicking elsewhere
            if (!popup.contains(e.target) && !e.target.classList.contains('info-button')) {
                hideInfoPopup();
            }

            // Handle node selection/action
            if (e.target.classList.contains('tree-node') || e.target.classList.contains('tree-label')) {
                const treeNode = e.target.closest('.tree-node');
                const itemData = JSON.parse(treeNode.dataset.item || '{}');

                // Remove previous selection
                document.querySelectorAll('.tree-node.selected').forEach(node => {
                    node.classList.remove('selected');
                });

                // Select current node
                treeNode.classList.add('selected');

                // Send message for actions (open project, show JSON, etc.)
                if (itemData.isProject) {
                    // Project nodes are opened via right-click context menu
                } else if (itemData.projectUrl && (!itemData.children || itemData.itemType === 'spec')) {
                    vscode.postMessage({
                        command: 'selectItem',
                        item: itemData
                    });
                }
            }
        });

        // Right-click context menu for project nodes
        document.addEventListener('contextmenu', (e) => {
            const treeNode = e.target.closest?.('.tree-node');
            if (treeNode) {
                const itemData = JSON.parse(treeNode.dataset.item || '{}');
                if (itemData.isProject) {
                    e.preventDefault();
                    contextMenuItem = itemData;

                    // Remove previous selection and select this node
                    document.querySelectorAll('.tree-node.selected').forEach(node => {
                        node.classList.remove('selected');
                    });
                    treeNode.classList.add('selected');

                    // Position and show the context menu
                    contextMenu.style.left = e.clientX + 'px';
                    contextMenu.style.top = e.clientY + 'px';
                    contextMenu.classList.add('visible');
                    return;
                }
            }
            hideContextMenu();
        });

        contextOpenBtn.addEventListener('click', () => {
            if (contextMenuItem) {
                vscode.postMessage({
                    command: 'openProject',
                    item: contextMenuItem
                });
            }
            hideContextMenu();
        });

        contextRemoveBtn.addEventListener('click', () => {
            if (contextMenuItem) {
                setLoading(true);
                vscode.postMessage({
                    command: 'removeProject',
                    item: contextMenuItem
                });
            }
            hideContextMenu();
        });

        function hideContextMenu() {
            contextMenu.classList.remove('visible');
            contextMenuItem = null;
        }

        document.addEventListener('click', (e) => {
            if (!contextMenu.contains(e.target)) {
                hideContextMenu();
            }
        });

        function showInfoPopup(button, itemData) {
            const rect = button.getBoundingClientRect();
            const container = document.getElementById('tree-container');
            const containerRect = container.getBoundingClientRect();

            // Position popup near the button
            popup.style.left = (rect.right - containerRect.left + 10) + 'px';
            popup.style.top = (rect.top - containerRect.top - 10) + 'px';

            // Set popup content
            popupTitle.textContent = itemData.key;

            let contentHtml = '';
            if (itemData.infoData && itemData.infoData.trim() !== '') {
                let doc = "";
                let link = "";
                try {
                    const info = JSON.parse(itemData.infoData);
                    doc = info.doc || "";
                    link = info.link || "";
                } catch (e) {
                    // Fallback for old format if any
                    const parts = itemData.infoData.split('\\n\\n');
                    doc = parts[0] || '';
                    link = parts[1] || '';
                }

                const docParts = doc.split('\\n').map(p => p.trim()).filter(p => p.length > 0);
                const summary = docParts.length > 0 ? docParts[0] : "";
                const extraParagraphs = docParts.length > 1 ? docParts.slice(1) : [];

                if (summary) {
                    contentHtml += '<div class="popup-section"><div class="section-content" style="font-weight: bold; margin-bottom: 8px;">' + summary + '</div></div>';
                }

                if (extraParagraphs.length > 0) {
                    contentHtml += '<div class="popup-section"><div class="section-content">';
                    extraParagraphs.forEach(p => {
                        contentHtml += '<p style="margin-top: 0; margin-bottom: 8px;">' + p + '</p>';
                    });
                    contentHtml += '</div></div>';
                }

                if (link) {
                    contentHtml += '<div class="popup-section"><div class="section-title">More Information</div><div class="section-content"><a href="' + link + '" class="popup-link" target="_blank">' + link + '</a></div></div>';
                }
            }

            if (!contentHtml) {
                contentHtml = '<div class="no-info">Information for ' + (itemData.itemType || 'item') + ' type "' + itemData.key + '" is not currently available.</div>';
            }

            popupContent.innerHTML = contentHtml;

            // Show popup
            popup.classList.add('visible');

            // Adjust position if popup goes off screen
            const popupRect = popup.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            if (popupRect.right > viewportWidth) {
                popup.style.left = (rect.left - containerRect.left - popupRect.width - 10) + 'px';
            }
            if (popupRect.bottom > viewportHeight) {
                popup.style.top = (rect.bottom - containerRect.top - popupRect.height + 10) + 'px';
            }
        }

        function hideInfoPopup() {
            popup.classList.remove('visible');
        }

        // Close popups on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideInfoPopup();
            }
        });
    </script>
</body>
</html>`;
}

function generateTreeHTML(node: TreeNode, level: number = 0): string {
	let html = '';

	if (node.children && node.children.length > 0) {
		// This is a parent node
		for (const child of node.children) {
			const hasChildren = child.children && child.children.length > 0;
			const nodeClass = getNodeClass(child);
			const iconClass = hasChildren ? 'tree-icon expandable' : 'tree-icon leaf';
			const hasInfo = child.itemType && (child.itemType === 'content' || child.itemType === 'artifact' || child.itemType === 'spec');
			const isArtifact = child.itemType === 'artifact';
			const itemDataJson = JSON.stringify(child).replace(/"/g, '&quot;');

			html += `
				<li class="tree-item">
					<div class="tree-node ${nodeClass}" data-item="${itemDataJson}">
						<span class="${iconClass}"></span>
						<span class="tree-label">${child.key}</span>
						${isArtifact ? `<button class="make-button" data-item="${itemDataJson}" title="Make artifact">Make</button>` : ''}
						${hasInfo ? `<button class="info-button" data-item="${itemDataJson}" title="Show information">i</button>` : ''}
					</div>
					${hasChildren ? `
						<ul class="tree-children">
							${generateTreeHTML(child, level + 1)}
						</ul>
					` : ''}
				</li>
			`;
		}
	}

	return html;
}

function getNodeClass(node: TreeNode): string {
	if (node.isProject) {
		return 'project-node';
	} else if (node.itemType === 'content') {
		return 'content-node';
	} else if (node.itemType === 'artifact') {
		return 'artifact-node';
	} else if (node.itemType === 'spec') {
		return 'spec-node';
	} else if (node.children && node.children.length > 0) {
		return 'folder-node';
	}
	return '';
}

function getInfoWebviewContent(title: string, infoData: string): string {
	let doc = "";
	let link = "";
	try {
		const info = JSON.parse(infoData);
		doc = info.doc || "";
		link = info.link || "";
	} catch (e) {
		// Fallback for old format if any
		const parts = infoData.split('\n\n');
		doc = parts[0] || '';
		link = parts[1] || '';
	}

	const docParts = doc.split('\n').map(p => p.trim()).filter(p => p.length > 0);
	const summary = docParts.length > 0 ? docParts[0] : "";
	const extraParagraphs = docParts.length > 1 ? docParts.slice(1) : [];

	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Information: ${title}</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            line-height: 1.5;
            padding: 20px;
            margin: 0;
        }
        .header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .info-icon {
            width: 24px;
            height: 24px;
            margin-right: 10px;
            border-radius: 50%;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 14px;
        }
        .title {
            font-size: 18px;
            font-weight: bold;
            margin: 0;
        }
        .content {
            margin-bottom: 20px;
        }
        .summary {
            font-weight: bold;
            margin-bottom: 15px;
        }
        .documentation {
            margin-bottom: 15px;
        }
        .documentation p {
            margin-top: 0;
            margin-bottom: 10px;
        }
        .link-container {
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid var(--vscode-panel-border);
        }
        .link {
            color: var(--vscode-textLink-foreground);
            text-decoration: none;
            word-break: break-all;
        }
        .link:hover {
            text-decoration: underline;
        }
        .section-title {
            font-weight: bold;
            margin-bottom: 5px;
            color: var(--vscode-descriptionForeground);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="info-icon">i</div>
        <h1 class="title">${title}</h1>
    </div>
    <div class="content">
        ${summary ? `<div class="summary">${summary}</div>` : ''}

        ${extraParagraphs.length > 0 ? `
        <div class="documentation">
            ${extraParagraphs.map(p => `<p>${p}</p>`).join('')}
        </div>
        ` : ''}

        ${link ? `
        <div class="link-container">
            <div class="section-title">More Information:</div>
            <a href="${link}" class="link" target="_blank">${link}</a>
        </div>
        ` : ''}

        ${!summary && extraParagraphs.length === 0 && !link ? '<div>No additional information available.</div>' : ''}
    </div>
</body>
</html>`;
}

// This method is called when your extension is deactivated
export function deactivate() {}
