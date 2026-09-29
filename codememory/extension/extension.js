const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

function activate(context) {
    const runsDir = path.join(context.extensionPath, '..', 'data', 'runs');
    let resultsFile = null;
    
    try {
        if (fs.existsSync(runsDir)) {
            const runs = fs.readdirSync(runsDir);
            const runName = runs.includes('werkzeug') ? 'werkzeug' : runs[0];
            resultsFile = path.join(runsDir, runName, 'results.json');
        } else {
            resultsFile = path.join(context.extensionPath, '..', 'data', 'results.json');
        }
        
        const data = JSON.parse(fs.readFileSync(resultsFile, 'utf8'));
        const hacks = data.hacks || [];
        
        let hoverProvider = vscode.languages.registerHoverProvider('python', {
            provideHover(document, position) {
                const line = document.lineAt(position.line).text;
                for (const hack of hacks) {
                    if (hack.what && line.includes(hack.what)) {
                        const md = new vscode.MarkdownString();
                        md.appendMarkdown(**CodeMemory Workaround ()**\n\n);
                        md.appendMarkdown(**Why:** \n\n);
                        md.appendMarkdown(**Status:** );
                        return new vscode.Hover(md);
                    }
                }
            }
        });
        
        context.subscriptions.push(hoverProvider);
    } catch (e) {
        console.error("CodeMemory extension error:", e);
    }
}
exports.activate = activate;
