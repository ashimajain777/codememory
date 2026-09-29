import argparse
import json
import os
import re
import uuid
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

from privacy_gate import PrivacyGate
from budget import global_budget
from ingest import get_hindsight, call_llm

DATA_DIR = Path(__file__).resolve().parent / 'data'
RUNS_DIR = DATA_DIR / 'runs'

def clone_repo(url_or_path, run_dir):
    repo_dir = run_dir / 'repo'
    is_local = os.path.isdir(url_or_path)
    if is_local:
        return Path(url_or_path), True
    else:
        if not repo_dir.exists():
            subprocess.check_call(['git', 'clone', '--depth', '1', url_or_path, str(repo_dir)])
        return repo_dir, False

def extract_candidates(repo_dir, max_candidates):
    candidates = []
    markers = ['HACK', 'FIXME', 'XXX', 'WORKAROUND', 'temporary', 'kludge', 'monkey-patch']
    for root, _, files in os.walk(repo_dir):
        if '.git' in root: continue
        for file in files:
            if not file.endswith(('.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.cs')):
                continue
            path = Path(root) / file
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines):
                if any(m in line for m in markers) or 'remove once' in line.lower() or 'remove when' in line.lower() or 'upstream bug' in line.lower():
                    snippet = "".join(lines[max(0, i-2):i+3])
                    candidates.append({
                        'file': str(path.relative_to(repo_dir)),
                        'line': i + 1,
                        'marker': line.strip(),
                        'snippet': snippet
                    })
    return candidates[:max_candidates]

def run():
    load_dotenv(Path(__file__).resolve().parent / '.env')
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--max-commits", type=int, default=300)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--privacy", choices=["redact", "block"], default="redact")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_name = args.repo.split('/')[-1].replace('.git', '')
    run_dir = RUNS_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    privacy_gate = PrivacyGate(mode=args.privacy, local_only=args.local_only)
    
    print(f"Scanning repo {args.repo}...")
    repo_dir, is_local = clone_repo(args.repo, run_dir)
    
    candidates = extract_candidates(repo_dir, args.max_candidates)
    print(f"Found {len(candidates)} candidates.")
    
    if args.dry_run:
        est_tokens = sum(len(c['snippet'])//4 for c in candidates)
        print(f"Dry run estimated tokens: {est_tokens}")
        return

    client = get_hindsight()
    bank_id = f"bank-{uuid.uuid4().hex[:8]}"
    
    results = {
        'meta': {
            'source': args.repo,
            'date': datetime.now(timezone.utc).isoformat(),
            'status': 'started',
            'usage': global_budget.usage,
            'privacy_summary': privacy_gate.generate_report()
        },
        'prs': [],
        'hacks': [],
        'impact': {}
    }
    
    # Save initial state
    with open(run_dir / 'results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Preflight
    try:
        global_budget.check_retain()
        client.retain(bank_id=bank_id, content="Preflight check", document_id="preflight-1")
        global_budget.record_retain()
        
        global_budget.check_recall()
        client.recall(bank_id=bank_id, query="Preflight")
        global_budget.record_recall()
        
        print("Preflight passed.")
    except Exception as e:
        print(f"Preflight failed: {e}")
        results['meta']['status'] = f"partial: {e}"
        with open(run_dir / 'results.json', 'w') as f:
            json.dump(results, f, indent=2)
        return

    # Assuming preflight passes
    # ... rest of the LLM logic ...
    
    results['meta']['status'] = 'success'
    with open(run_dir / 'results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Done. Saved to {run_dir / 'results.json'}")

if __name__ == '__main__':
    run()
