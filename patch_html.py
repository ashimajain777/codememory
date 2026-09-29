import re

html_path = 'codememory/web/index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Let's insert the impact panel before the PR view
impact_panel = """
    <!-- IMPACT PANEL -->
    <div id="impact-panel" style="padding: 20px; display: none;">
      <h2>Project Impact & Memory</h2>
      <div id="impact-stats" style="margin-top: 10px; padding: 15px; border: 1px solid var(--rule); background: var(--panel);">
        Loading impact...
      </div>
    </div>
"""

# Replace <div class="pr-view" id="pr-view"> with the panel + pr-view
if 'id="impact-panel"' not in content:
    content = content.replace('<div class="pr-view" id="pr-view">', impact_panel + '\n    <div class="pr-view" id="pr-view">')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Added impact panel to index.html")
else:
    print("Impact panel already present")
