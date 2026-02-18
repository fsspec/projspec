// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { execSync } from "node:child_process";

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
    // /Users/mdurant/code/projspec

	console.log('Congratulations, your extension "projspec" is now active!');
}

// This method is called when your extension is deactivated
export function deactivate() {}

function to_html(path: String): String {
	let out = execSync("projspec --html-out " + path.substring(18), { stdio: 'pipe' });
	return out.toString();
}
