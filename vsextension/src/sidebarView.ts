import * as vscode from 'vscode';

/**
 * Simple sidebar view that provides a button to launch the main Project
 * Library webview panel.  Keeping this view lightweight (just a command
 * trigger) leaves the full two-panel UI to be rendered in a roomy editor-area
 * WebviewPanel, as described in ACTIONS.md.
 */
export class SidebarViewProvider implements vscode.WebviewViewProvider {
    constructor(private readonly _extensionUri: vscode.Uri) {}

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this.getHtml();
        webviewView.webview.onDidReceiveMessage((msg) => {
            if (msg.cmd === 'open') {
                vscode.commands.executeCommand('projspec.showTree');
            }
        });
    }

    private getHtml(): string {
        return /* html */ `
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
    body { font-family: var(--vscode-font-family); padding: 12px; }
    button {
        background: var(--vscode-button-background);
        color: var(--vscode-button-foreground);
        border: none;
        padding: 8px 14px;
        cursor: pointer;
        border-radius: 3px;
        font-size: 13px;
        width: 100%;
    }
    button:hover { background: var(--vscode-button-hoverBackground); }
    p { color: var(--vscode-descriptionForeground); font-size: 12px; }
</style>
</head>
<body>
    <p>projspec manages a library of projects, scans directories for known
    project types, and can build/run their artifacts.</p>
    <button onclick="acquireVsCodeApi().postMessage({cmd:'open'})">Open Project Library</button>
</body>
</html>`;
    }
}
