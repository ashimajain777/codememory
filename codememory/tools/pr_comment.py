"""
Print the markdown a GitHub Action would post for a given PR.

Usage: python tools/pr_comment.py <pr_number>

Reads data/results.json and outputs the formatted review comments
that CodeMemory would post on the specified PR.
"""

import json
import sys
from pathlib import Path

RESULTS_FILE = Path(__file__).resolve().parent.parent / "data" / "results.json"


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/pr_comment.py <pr_number>")
        sys.exit(1)

    pr_num = int(sys.argv[1])

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    pr = None
    for p in data["prs"]:
        if p["pr"] == pr_num:
            pr = p
            break

    if pr is None:
        print(f"PR #{pr_num} not found in results.json")
        sys.exit(1)

    if not pr["comments"]:
        print(f"PR #{pr_num}: No CodeMemory comments.")
        return

    print(f"# CodeMemory Review: PR #{pr_num} - {pr['title']}")
    print(f"Branch: `{pr['branch']}` -> `main`")
    print(f"Author: {pr['author']} | Date: {pr['date'].split('T')[0]}")
    print()

    for comment in pr["comments"]:
        kind = comment["kind"].replace("_", " ").title()
        print(f"## [{kind}] {comment.get('id', '')}")
        print()

        if comment.get("path"):
            print(f"File: `{comment['path']}`")

        if comment.get("anchor_snippet"):
            print("```python")
            print(comment["anchor_snippet"].split("\n")[0])
            print("```")

        print()
        print(comment["body_md"])
        print()

        if comment.get("checker"):
            c = comment["checker"]
            print(f"**Reality Checker**: {c['verdict']} (confidence: {c['confidence']:.0%})")
            if c.get("counter_arguments"):
                print("Counter-arguments:")
                for ca in c["counter_arguments"]:
                    print(f"  - {ca}")
            print()

        if comment.get("sql_baseline"):
            sb = comment["sql_baseline"]
            print(f"**SQL baseline**: `{sb['query']}`")
            if sb["rows"]:
                print(f"  Result: {json.dumps(sb['rows'])}")
            else:
                print("  Result: 0 rows (no shared ticket)")
            print()

        if comment.get("suggestion"):
            s = comment["suggestion"]
            print(f"**Suggestion**: {s['summary']}")
            print(f"  Proposal: {s['proposal']}")
            print(f"  Affects: {', '.join(s['hack_ids'])}")
            print()

        print("---")
        print()


if __name__ == "__main__":
    main()
