import json
import os
import unittest
from pathlib import Path
import re

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
RUNS_DIR = DATA_DIR / 'runs'

class TestCodeMemory(unittest.TestCase):
    def setUp(self):
        # Find latest run
        runs = list(RUNS_DIR.glob('*/results.json'))
        if not runs:
            results_file = DATA_DIR / 'results.json'
        else:
            runs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            results_file = runs[0]

        if not results_file.exists():
            self.results = {'meta': {}, 'prs': [], 'hacks': [], 'impact': {}}
        else:
            with open(results_file, 'r', encoding='utf-8') as f:
                self.results = json.load(f)

    def test_schema_valid(self):
        self.assertIn('meta', self.results)
        self.assertIn('prs', self.results)
        self.assertIn('hacks', self.results)
        self.assertIn('impact', self.results)

    def test_invariants_real_run(self):
        meta = self.results.get('meta', {})
        if meta.get('source') == 'synthetic-fixture':
            return
            
        status = meta.get('status', '')
        if 'partial' not in status and 'success' in status:
            usage = meta.get('usage', {})
            self.assertTrue(usage.get('llm_calls', 0) > 0, "Real successful run must have LLM calls")
            self.assertTrue(usage.get('recalls', 0) > 0, "Real successful run must have recalls")
            
        hacks = self.results.get('hacks', [])
        impact = self.results.get('impact', {})
        if impact and hacks:
            self.assertEqual(impact.get('workarounds_found', 0), len(hacks))
            
    def test_no_mock_markers(self):
        import glob
        for py_file in glob.glob(str(Path(__file__).parent.parent / '*.py')):
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertFalse(re.search(r'\bDummy\w*', content), f"Found Dummy in {py_file}")
                self.assertFalse(re.search(r'\bpatch_\w*', content), f"Found patch_ in {py_file}")

    def test_synthetic_fixture(self):
        meta = self.results.get('meta', {})
        if meta.get('source') != 'synthetic-fixture':
            self.skipTest("Not synthetic fixture")
        
        prs = {int(pr.get('pr', 0)): pr for pr in self.results.get('prs', [])}
        pr24 = prs.get(24)
        self.assertIsNotNone(pr24)
        resolves_comments = [c for c in pr24.get('comments', []) if c.get('kind') == 'resolves' and 'HACK-006' in c.get('body_md', '')]
        self.assertTrue(len(resolves_comments) > 0, "PR 24 should resolve HACK-006")

if __name__ == '__main__':
    unittest.main()
