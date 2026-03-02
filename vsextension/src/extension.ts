// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { execSync } from "node:child_process";

interface TreeNode {
	key: string;
	children?: TreeNode[];
	data?: any;
	tooltip?: string;
	isProject?: boolean;
	projectUrl?: string;
}

const openDocuments = new Map<string, vscode.TextDocument>();

function buildTreeNodes(projectUrl: string, project: any): TreeNode[] {
	const projectChildren: TreeNode[] = [];

	// Top-level contents
	if (project.contents && Object.keys(project.contents).length > 0) {
		const contentChildren: TreeNode[] = [];
		for (const [name, _] of Object.entries(project.contents)) {
			const basename = name.split('/').pop() || name;
			contentChildren.push({ key: basename, tooltip: name, projectUrl });
		}
		projectChildren.push({ key: "contents", children: contentChildren });
	}

	// Top-level artifacts
	if (project.artifacts && Object.keys(project.artifacts).length > 0) {
		const artifactChildren: TreeNode[] = [];
		for (const [name, _] of Object.entries(project.artifacts)) {
			const basename = name.split('/').pop() || name;
			artifactChildren.push({ key: basename, tooltip: name, projectUrl });
		}
		projectChildren.push({ key: "artifacts", children: artifactChildren });
	}

	// Specs - only show spec names, not their details
	if (project.specs && Object.keys(project.specs).length > 0) {
		const specsChildren: TreeNode[] = [];
		for (const [specName, _] of Object.entries(project.specs as Record<string, any>)) {
			specsChildren.push({ key: specName, projectUrl });
		}
		projectChildren.push({ key: "specs", children: specsChildren });
	}

	return projectChildren;
}

function getExampleData(): TreeNode {
	try {
		const out = execSync("projspec library list --json-out", { stdio: 'pipe', encoding: 'utf-8' });
		const data = JSON.parse(out) as Record<string, any>;

		const children: TreeNode[] = [];

		// Data is a dict of project_url -> project_data
		for (const [projectUrl, project] of Object.entries(data)) {
			const projectChildren = buildTreeNodes(projectUrl, project);

			// Extract basename from project URL for display
			const projectBasename = projectUrl.split('/').pop() || projectUrl;
			children.push({ key: projectBasename, tooltip: projectUrl, children: projectChildren, data: project, isProject: true });
		}

		return { key: "projects", children };
	} catch (error) {
		return {
			key: "projects",
			children: [
				{
					key: "project-alpha",
					tooltip: "https://example.com/project-alpha",
					projectUrl: "https://example.com/project-alpha",
					children: [
						{ key: "contents", children: [{ key: "README.md", tooltip: "README.md", projectUrl: "https://example.com/project-alpha" }, { key: "setup.py", tooltip: "setup.py", projectUrl: "https://example.com/project-alpha" }] },
						{ key: "artifacts", children: [{ key: "dist/pkg.tar", tooltip: "dist/pkg.tar", projectUrl: "https://example.com/project-alpha" }] },
						{
							key: "specs",
							children: [
								{ key: "v1.0.0", projectUrl: "https://example.com/project-alpha" },
								{ key: "v2.0.0", projectUrl: "https://example.com/project-alpha" }
							]
						}
					]
				}
			]
		};
	}
}

class ProjectTreeDataProvider implements vscode.TreeDataProvider<TreeNode> {
	private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
	readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

	constructor() {}

	refresh(): void {
		this._onDidChangeTreeData.fire();
	}

	getTreeItem(element: TreeNode): vscode.TreeItem {
		const item = new vscode.TreeItem(element.key);
		if (element.children && element.children.length > 0) {
			item.collapsibleState = vscode.TreeItemCollapsibleState.Collapsed;
		} else {
			item.collapsibleState = vscode.TreeItemCollapsibleState.None;
		}
		if (element.tooltip) {
			item.tooltip = element.tooltip;
		}
		if (element.isProject) {
			item.contextValue = 'project';
		}
		// Set command for leaf nodes that belong to a project
		if (!element.isProject && element.projectUrl && !element.children) {
			item.command = {
				command: 'projspec.showItem',
				arguments: [element],
				title: 'Show Item'
			};
		}
		return item;
	}

	getChildren(element?: TreeNode): TreeNode[] {
		if (!element) {
			return getExampleData().children || [];
		}
		return element.children || [];
	}
}

export function activate(context: vscode.ExtensionContext) {

	// register a content provider for scheme
	const myScheme = 'projspec';
	const myProvider = new class implements vscode.TextDocumentContentProvider {

		// emitter and its event
		onDidChangeEmitter = new vscode.EventEmitter<vscode.Uri>();
		onDidChange = this.onDidChangeEmitter.event;

		provideTextDocumentContent(uri: vscode.Uri): string {
			const out = execSync("projspec --html-out " + uri.toString().substring(18), { stdio: 'pipe' });
			return uri.toString().substring(18) + out;
		}
	};

	context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider(myScheme, myProvider));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.scan', async () => {
		if (vscode.workspace.workspaceFolders !== undefined) {
			const folderPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
			const uri = vscode.Uri.file(folderPath);
			let text = vscode.Uri.parse("projspec:" + uri);

			const panel = vscode.window.createWebviewPanel("projspec", folderPath, vscode.ViewColumn.One, {});
			panel.webview.html = "<!DOCTYPE html><html><body>" + to_html(text.toString()) + "</body></html>";
			console.log(folderPath);
		}
		else {return;};
	}));

	const treeDataProvider = new ProjectTreeDataProvider();
	context.subscriptions.push(vscode.window.registerTreeDataProvider('projspec-projects', treeDataProvider));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showTree', async () => {
		treeDataProvider.refresh();
		await vscode.commands.executeCommand('projspec-projects.focus');
	}));

	context.subscriptions.push(vscode.commands.registerCommand('projspec.openProject', async (item: TreeNode) => {
		if (!item || !item.tooltip) {
			return;
		}

		const projectUrl = item.tooltip;

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

	context.subscriptions.push(vscode.commands.registerCommand('projspec.showItem', async (item: TreeNode) => {
		if (!item || !item.projectUrl) {
			return;
		}

		try {
			const out = execSync("projspec library list --json-out", { stdio: 'pipe', encoding: 'utf-8' });
			const data = JSON.parse(out) as Record<string, any>;
			const projectData = data[item.projectUrl];

			if (!projectData) {
				vscode.window.showErrorMessage(`Project not found: ${item.projectUrl}`);
				return;
			}

			const jsonContent = JSON.stringify(projectData, null, 2);

			// Check if document is already open
			const existingDoc = openDocuments.get(item.projectUrl);
			let doc: vscode.TextDocument;

			if (existingDoc) {
				doc = existingDoc;
			} else {
				doc = await vscode.workspace.openTextDocument({
					language: 'json',
					content: jsonContent
				});
				openDocuments.set(item.projectUrl, doc);
			}

			const editor = await vscode.window.showTextDocument(doc, {
				preview: false,
				viewColumn: vscode.ViewColumn.One
			});

			// Try to find and reveal the item in the JSON
			const text = doc.getText();
			const searchKey = item.tooltip || item.key;

			if (searchKey) {
				const searchText = searchKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
				const regex = new RegExp(`"${searchText}"`);
				const match = text.match(regex);

				if (match) {
					const start = doc.positionAt(match.index!);
					const end = doc.positionAt(match.index! + match[0].length);
					const range = new vscode.Range(start, end);
					editor.selection = new vscode.Selection(start, end);
					editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
				}
			}
		} catch (error) {
			vscode.window.showErrorMessage(`Failed to load project: ${error}`);
		}
	}));

	console.log('Congratulations, your extension "projspec" is now active!');
}

// This method is called when your extension is deactivated
export function deactivate() {}

function to_html(path: String): String {
	let out = execSync("projspec --html-out " + path.substring(18), { stdio: 'pipe' });
	return out.toString();
}
