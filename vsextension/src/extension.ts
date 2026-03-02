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
		const data = JSON.parse(out);

		const children: TreeNode[] = [];
		for (const [key, project] of Object.entries(data)) {
			const projectChildren: TreeNode[] = [];

			// Top-level contents
			if (project.contents && project.contents.length > 0) {
				projectChildren.push({
					key: "contents",
					children: project.contents.map((c: string) => ({ key: c }))
				});
			}

			// Top-level artifacts
			if (project.artifacts && project.artifacts.length > 0) {
				projectChildren.push({
					key: "artifacts",
					children: project.artifacts.map((a: string) => ({ key: a }))
				});
			}

			// Specs
			if (project.specs && project.specs.length > 0) {
				const specsChildren: TreeNode[] = [];
				for (const spec of project.specs) {
					const specChildren: TreeNode[] = [];
					if (spec.contents && spec.contents.length > 0) {
						specChildren.push({
							key: "contents",
							children: spec.contents.map((c: string) => ({ key: c }))
						});
					}
					if (spec.artifacts && spec.artifacts.length > 0) {
						specChildren.push({
							key: "artifacts",
							children: spec.artifacts.map((a: string) => ({ key: a }))
						});
					}
					specsChildren.push({ key: spec.name, children: specChildren });
				}
				projectChildren.push({ key: "specs", children: specsChildren });
			}

			children.push({ key: project.key, children: projectChildren });
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
    // /Users/mdurant/code/projspec

	console.log('Congratulations, your extension "projspec" is now active!');
}

// This method is called when your extension is deactivated
export function deactivate() {}

function to_html(path: String): String {
	let out = execSync("projspec --html-out " + path.substring(18), { stdio: 'pipe' });
	return out.toString();
}
