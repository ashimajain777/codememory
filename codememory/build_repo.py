"""
Replays plot.py PR history into sample_repo/ as a real git repository.
Sets GIT_AUTHOR_DATE and GIT_AUTHOR_NAME per commit.
After replay, writes data/commits.json from git log and git diff.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add parent to path so we can import data.plot
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.plot import PRS

REPO_DIR = Path(__file__).resolve().parent / "sample_repo"
COMMITS_FILE = Path(__file__).resolve().parent / "data" / "commits.json"


def run_git(args, cwd, env=None):
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=merged_env,
    )
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed: {result.stderr}", file=sys.stderr)
    return result


def build_repo():
    # Clean and init
    if REPO_DIR.exists():
        shutil.rmtree(REPO_DIR)
    REPO_DIR.mkdir(parents=True)
    run_git(["init"], REPO_DIR)
    run_git(["config", "user.email", "bot@codememory.dev"], REPO_DIR)
    run_git(["config", "user.name", "CodeMemory Bot"], REPO_DIR)

    # Track commit SHAs
    commits = []

    for pr in PRS:
        pr_num = pr["pr_number"]
        author = pr["author"]
        date = pr["date"]
        message = pr["message"]
        branch = pr["branch"]
        files = pr.get("files", {})

        # Author env
        git_env = {
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
            "GIT_AUTHOR_NAME": author,
            "GIT_COMMITTER_NAME": author,
            "GIT_AUTHOR_EMAIL": author.lower().replace(" ", ".") + "@example.com",
            "GIT_COMMITTER_EMAIL": author.lower().replace(" ", ".") + "@example.com",
        }

        # Apply file changes
        for filepath, content in files.items():
            full_path = REPO_DIR / filepath
            if content is None:
                # Delete file
                if full_path.exists():
                    full_path.unlink()
                    run_git(["rm", filepath], REPO_DIR, env=git_env)
            else:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                run_git(["add", filepath], REPO_DIR, env=git_env)

        # Skip empty commits for noise PRs with no file changes
        if not files:
            # Create a tiny change in a marker file
            marker = REPO_DIR / ".pr_marker"
            marker.write_text(f"PR-{pr_num}\n", encoding="utf-8")
            run_git(["add", ".pr_marker"], REPO_DIR, env=git_env)

        # Commit
        commit_msg = f"PR #{pr_num}: {message}"
        if pr.get("closes_ticket"):
            commit_msg += f"\n\nCloses {pr['closes_ticket']}"
        run_git(["commit", "-m", commit_msg, "--allow-empty"], REPO_DIR, env=git_env)

        # Get SHA
        result = run_git(["rev-parse", "HEAD"], REPO_DIR)
        sha = result.stdout.strip()

        # Get diff for this commit
        diff_result = run_git(["diff", "HEAD~1..HEAD", "--no-color"], REPO_DIR)
        diff_text = diff_result.stdout if diff_result.returncode == 0 else ""
        # First commit has no HEAD~1
        if pr_num == 1:
            diff_result = run_git(["diff", "--cached", "HEAD", "--no-color"], REPO_DIR)
            diff_result2 = run_git(
                ["show", "--format=", "--no-color", sha], REPO_DIR
            )
            diff_text = diff_result2.stdout if diff_result2.returncode == 0 else ""

        # Build files_after: current state of all tracked files
        ls_result = run_git(["ls-files"], REPO_DIR)
        files_after = {}
        for fname in ls_result.stdout.strip().split("\n"):
            fname = fname.strip()
            if not fname:
                continue
            fpath = REPO_DIR / fname
            if fpath.exists():
                try:
                    files_after[fname] = fpath.read_text(encoding="utf-8")
                except Exception:
                    pass

        commits.append({
            "pr_number": pr_num,
            "sha": sha,
            "title": pr["title"],
            "branch": branch,
            "author": author,
            "date": date,
            "message": message,
            "closes_ticket": pr.get("closes_ticket"),
            "diff": diff_text,
            "files_after": files_after,
        })

        print(f"  PR #{pr_num} ({sha[:8]}): {pr['title']}")

    # Write commits.json
    COMMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(commits, f, indent=2)

    print(f"\nWrote {len(commits)} commits to {COMMITS_FILE}")
    print(f"Repository at {REPO_DIR}")


if __name__ == "__main__":
    build_repo()
