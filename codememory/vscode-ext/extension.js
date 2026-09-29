const vscode = require('vscode');
const fs = require('fs');

let hacksData = [];
let prsData = [];
let watcher = null;
let decorationType = null;

function loadResults(resultsPath) {
    if (!resultsPath || !fs.existsSync(resultsPath)) {
        hacksData = [];
        prsData = [];
        return;
    }
    try {
        const data = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
        hacksData = data.hacks || [];
        prsData = data.prs || [];
        console.log("CodeMemory: loaded " + hacksData.length + " hacks.");
    } catch (err) {
        console.error("CodeMemory: Failed to parse results.json", err);
    }
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function updateDecorations(editor) {
    if (!editor || !decorationType) return;
    const docText = editor.document.getText();
    const decorations = [];

    for (const hack of hacksData) {
        if (!hack.anchor_snippet || hack.status === 'retired') continue;
        
        const snippetTokens = hack.anchor_snippet.trim().split(/\s+/).filter(Boolean);
        if (snippetTokens.length === 0) continue;
        
        const snippetPattern = snippetTokens.map(escapeRegExp).join('\\s+');
        const regex = new RegExp(snippetPattern, 'g');
        
        let match;
        while ((match = regex.exec(docText)) !== null) {
            const startPos = editor.document.positionAt(match.index);
            const endPos = editor.document.positionAt(match.index + match[0].length);
            decorations.push({ range: new vscode.Range(startPos, endPos) });
        }
    }
    
    editor.setDecorations(decorationType, decorations);
}

function activate(context) {
    const config = vscode.workspace.getConfiguration('codememory');
    const resultsPath = config.get('resultsPath');
    
    loadResults(resultsPath);

    if (resultsPath && fs.existsSync(resultsPath)) {
        watcher = fs.watch(resultsPath, (eventType) => {
            if (eventType === 'change') {
                loadResults(resultsPath);
                if (vscode.window.activeTextEditor) {
                    updateDecorations(vscode.window.activeTextEditor);
                }
            }
        });
        context.subscriptions.push({ dispose: () => { if(watcher) watcher.close(); } });
    }

    decorationType = vscode.window.createTextEditorDecorationType({
        textDecoration: 'underline dotted var(--vscode-editorError-foreground)'
    });
    context.subscriptions.push(decorationType);

    if (vscode.window.activeTextEditor) {
        updateDecorations(vscode.window.activeTextEditor);
    }

    vscode.window.onDidChangeActiveTextEditor(editor => {
        updateDecorations(editor);
    }, null, context.subscriptions);

    vscode.workspace.onDidChangeTextDocument(event => {
        if (vscode.window.activeTextEditor && event.document === vscode.window.activeTextEditor.document) {
            updateDecorations(vscode.window.activeTextEditor);
        }
    }, null, context.subscriptions);

    const hoverProvider = vscode.languages.registerHoverProvider('python', {
        provideHover(document, position, token) {
            const docText = document.getText();
            const hoverOffset = document.offsetAt(position);
            
            for (const hack of hacksData) {
                if (!hack.anchor_snippet) continue;
                
                const snippetTokens = hack.anchor_snippet.trim().split(/\s+/).filter(Boolean);
                if (snippetTokens.length === 0) continue;
                
                const snippetPattern = snippetTokens.map(escapeRegExp).join('\\s+');
                const regex = new RegExp(snippetPattern, 'g');
                
                let match;
                while ((match = regex.exec(docText)) !== null) {
                    const start = match.index;
                    const end = match.index + match[0].length;
                    
                    if (hoverOffset >= start && hoverOffset <= end) {
                        let prData = prsData.find(p => p.pr === hack.pr_added) || {};
                        let md = new vscode.MarkdownString();
                        md.appendMarkdown(`**CodeMemory**: ${hack.what}\n\n`);
                        md.appendMarkdown(`**Why it exists**: ${hack.why}\n\n`);
                        md.appendMarkdown(`**Removal condition**: ${hack.revisit_condition}\n\n`);
                        md.appendMarkdown(`**Risk**: ${hack.risk}\n\n`);
                        
                        let author = prData.author || "Unknown";
                        let date = prData.date ? new Date(prData.date).toLocaleDateString() : "Unknown";
                        md.appendMarkdown(`Added by **${author}** on ${date} (PR #${hack.pr_added})\n\n`);
                        
                        if (hack.status !== 'open' && hack.status_since_pr) {
                            md.appendMarkdown(`**Status**: ${hack.status} (since PR #${hack.status_since_pr})\n\n`);
                        } else {
                            md.appendMarkdown(`**Status**: ${hack.status}\n\n`);
                        }
                        
                        return new vscode.Hover(md);
                    }
                }
            }
            return null;
        }
    });

    context.subscriptions.push(hoverProvider);
}

function deactivate() {
    if (watcher) watcher.close();
}

module.exports = {
    activate,
    deactivate
};
