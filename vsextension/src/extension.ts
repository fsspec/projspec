import * as vscode from 'vscode';
import { ProjspecPanel } from './panel';
import { SidebarViewProvider } from './sidebarView';

export function activate(context: vscode.ExtensionContext): void {
    const sidebarProvider = new SidebarViewProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('projspec.view', sidebarProvider)
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('projspec.showTree', () => {
            ProjspecPanel.createOrShow(context.extensionUri);
        })
    );
}

export function deactivate(): void {
    // nothing to clean up
}
