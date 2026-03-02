// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { execSync } from "node:child_process";

interface TreeNode {
	key: string;
	children?: TreeNode[];
}

function getExampleData(): TreeNode {
	try {
		const out = execSync("projspec library list --json-out", { stdio: 'pipe', encoding: 'utf-8' });
		const data = JSON.parse(out) as Record<string, any>;

		const children: TreeNode[] = [];

		// Data is a dict of project_url -> project_data
		for (const [projectUrl, project] of Object.entries(data)) {
			const projectChildren: TreeNode[] = [];

			// Top-level contents
			if (project.contents && Object.keys(project.contents).length > 0) {
				const contentChildren: TreeNode[] = [];
				for (const [name, _] of Object.entries(project.contents)) {
					contentChildren.push({ key: name });
				}
				projectChildren.push({ key: "contents", children: contentChildren });
			}

			// Top-level artifacts
			if (project.artifacts && Object.keys(project.artifacts).length > 0) {
				const artifactChildren: TreeNode[] = [];
				for (const [name, _] of Object.entries(project.artifacts)) {
					artifactChildren.push({ key: name });
				}
				projectChildren.push({ key: "artifacts", children: artifactChildren });
			}

			// Specs
			if (project.specs && Object.keys(project.specs).length > 0) {
				const specsChildren: TreeNode[] = [];
				for (const [specName, spec] of Object.entries(project.specs as Record<string, any>)) {
					const specChildren: TreeNode[] = [];

					// Spec contents
					if (spec._contents && Object.keys(spec._contents).length > 0) {
						const specContentChildren: TreeNode[] = [];
						for (const [name, _] of Object.entries(spec._contents as Record<string, any>)) {
							specContentChildren.push({ key: name });
						}
						specChildren.push({ key: "contents", children: specContentChildren });
					}

					// Spec artifacts
					if (spec._artifacts && Object.keys(spec._artifacts).length > 0) {
						const specArtifactChildren: TreeNode[] = [];
						for (const [name, _] of Object.entries(spec._artifacts as Record<string, any>)) {
							specArtifactChildren.push({ key: name });
						}
						specChildren.push({ key: "artifacts", children: specArtifactChildren });
					}

					specsChildren.push({ key: specName, children: specChildren });
				}
				projectChildren.push({ key: "specs", children: specsChildren });
			}

			children.push({ key: projectUrl, children: projectChildren });
		}

		return { key: "projects", children };
	} catch (error) {
		return {
			key: "projects",
			children: [
				{
					key: "https://example.com/project-alpha",
					children: [
						{ key: "contents", children: [{ key: "README.md" }, { key: "setup.py" }] },
						{ key: "artifacts", children: [{ key: "dist/pkg.tar" }] },
						{
							key: "specs",
							children: [
								{
									key: "v1.0.0",
									children: [
										{ key: "contents", children: [{ key: "spec.md" }] },
										{ key: "artifacts", children: [{ key: "output.html" }] }
									]
								}
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
		// const what = await vscode.window.showInputBox({ placeHolder: 'where...' });
		if (vscode.workspace.workspaceFolders !== undefined) {
			const folderPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
			const uri = vscode.Uri.file(folderPath);
			// vscode.commands.executeCommand('vscode.openFolder', uri, { forceReuseWindow: true });
			let text = vscode.Uri.parse("projspec:" + uri);

			// text format
			// const doc = await vscode.workspace.openTextDocument(text);
			//await vscode.window.showTextDocument(doc, { preview: false });

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
		if (!item || !item.key) {
			return;
		}

		const projectUrl = item.key;

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
    // /Users/mdurant/code/projspec

	console.log('Congratulations, your extension "projspec" is now active!');
}

// This method is called when your extension is deactivated
export function deactivate() {}

function to_html(path: String): String {
	let out = execSync("projspec --html-out " + path.substring(18), { stdio: 'pipe' });
	return out.toString();
}
