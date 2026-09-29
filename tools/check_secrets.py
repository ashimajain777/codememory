import os
import sys
import subprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from codememory.privacy_gate import PrivacyGate

def get_tracked_files():
    try:
        output = subprocess.check_output(['git', 'ls-files'], text=True)
        return [f for f in output.split('\n') if f and os.path.exists(f)]
    except Exception:
        return []

def get_untracked_files():
    try:
        output = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True)
        return [f for f in output.split('\n') if f and os.path.exists(f)]
    except Exception:
        return []

def run():
    files = get_tracked_files() + get_untracked_files()
    gate = PrivacyGate(mode='report')
    for fpath in files:
        if os.path.isdir(fpath) or not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            gate.process_text(content, fpath)
        except Exception:
            pass # skip binaries
            
    report = gate.generate_report()
    for detail in report['details']:
        print(detail)
    print(f"Total findings: {len(report['details'])}")

if __name__ == '__main__':
    run()
