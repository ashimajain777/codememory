import argparse
import shutil
from pathlib import Path
import json

DATA_DIR = Path(__file__).resolve().parent.parent / 'codememory' / 'data'
RUNS_DIR = DATA_DIR / 'runs'
WEB_DIR = Path(__file__).resolve().parent.parent / 'codememory' / 'web'

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_name")
    args = parser.parse_args()

    run_json = RUNS_DIR / args.run_name / 'results.json'
    if not run_json.exists():
        print(f"Run not found: {run_json}")
        return

    # Update web/app.js to fetch from the specific run
    app_js_path = WEB_DIR / 'app.js'
    if app_js_path.exists():
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # replace fetch('../data/results.json') with fetch('../data/runs/{run_name}/results.json')
        import re
        content = re.sub(r"fetch\(['\"].*?results\.json['\"]\)", f"fetch('../data/runs/{args.run_name}/results.json')", content)
        with open(app_js_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    # Remove web/results.json if it exists
    web_json = WEB_DIR / 'results.json'
    if web_json.exists():
        web_json.unlink()
        
    print(f"Active run set to {args.run_name}")

if __name__ == '__main__':
    run()
