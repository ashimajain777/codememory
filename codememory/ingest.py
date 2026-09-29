"""
CodeMemory ingestion pipeline.

Processes PRs chronologically, mimicking pre-merge review. For each PR:
1. Recall: query Hindsight with touched files/functions and semantic paraphrase
2. Classify: determine if PR introduces a workaround (via Groq LLM)
3. Resolve-check: test if PR resolves any open hack (Reality Checker gate)
4. Cross-hack reflect: if adding a workaround, check for root-cause patterns

Caches LLM calls by content hash. Supports --limit N and --resume.
"""

import hashlib
import json
import os
import sys
import time
import re
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from personas import REALITY_CHECKER, ONBOARDING_ENGINEER

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "qwen/qwen3.8-27b"
import uuid
BANK_ID = f"payments-service-{uuid.uuid4().hex[:8]}"
HINDSIGHT_BASE_URL = os.environ.get("HINDSIGHT_BASE_URL", "")
HINDSIGHT_API_KEY = os.environ.get("HINDSIGHT_API_KEY", "")
DATA_DIR = Path(__file__).resolve().parent / "data"
COMMITS_FILE = DATA_DIR / "commits.json"
RESULTS_FILE = DATA_DIR / "results.json"
CACHE_DIR = DATA_DIR / "cache"
LOG_FILE = DATA_DIR / "pipeline.log"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_lines = []

def log(pr_num, kind, text):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] PR#{pr_num} {kind}: {text}"
    _log_lines.append({"pr": pr_num, "ts": ts, "kind": kind, "text": text})
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---------------------------------------------------------------------------
# Groq LLM wrapper with retry, JSON mode, backoff
# ---------------------------------------------------------------------------
def _groq_client():
    from groq import Groq
    return Groq(api_key=GROQ_API_KEY)

def _cache_key(messages, temperature=0):
    raw = json.dumps(messages, sort_keys=True) + str(temperature) + GROQ_MODEL
    return hashlib.sha256(raw.encode()).hexdigest()

def _snippet_in(snippet, content):
    if not snippet: return False
    sl = [l.strip() for l in snippet.split('\n') if l.strip()]
    cl = [l.strip() for l in content.split('\n')]
    if not sl: return False
    for i in range(len(cl) - len(sl) + 1):
        if cl[i:i+len(sl)] == sl: return True
    return False


def hindsight_retain(content, document_id=None):
    client = get_hindsight()
    # Note: Using client.retain_batch directly, or if using client.retain wait for proper kwargs
    # Wait, the instruction says: reimplement using real shapes.
    # The original was: _hindsight_retry_loop(client.retain, bank_id=BANK_ID, content=content, document_id=document_id)
    return _hindsight_retry_loop(client.retain, bank_id=BANK_ID, content=content, document_id=document_id)

def hindsight_recall(query, top_k=5):
    client = get_hindsight()
    resp = _hindsight_retry_loop(client.recall, bank_id=BANK_ID, query=query)
    if hasattr(resp, 'results') and resp.results:
        resp.results = resp.results[:top_k]
    count = len(resp.results) if hasattr(resp, 'results') and resp.results else 0
    print(f"    [Recall] query: {query[:50]}... | Raw result count: {count}")
    return resp

def hindsight_reflect(query):
    client = get_hindsight()
    return _hindsight_retry_loop(client.reflect, bank_id=BANK_ID, query=query)

def call_llm(messages, temperature=0, json_mode=True, pr_num=0):
    """Call Groq LLM with caching, retry on JSON parse failure, 429 backoff."""
    cache_hash = _cache_key(messages, temperature)
    cache_path = CACHE_DIR / f"{cache_hash}.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    client = _groq_client()
    kwargs = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    attempt = 0
    while True:
        try:
            resp = client.chat.completions.create(**kwargs)
            if hasattr(resp, "usage") and resp.usage:
                log(pr_num, "usage", f"tokens: {resp.usage.total_tokens}")
            text = resp.choices[0].message.content
            if json_mode:
                try:
                    result = json.loads(text)
                except json.JSONDecodeError:
                    if attempt == 0:
                        # Retry once with explicit JSON instruction
                        messages_retry = messages + [
                            {"role": "user", "content": "Return valid JSON only, no prose"}
                        ]
                        resp2 = client.chat.completions.create(
                            model=GROQ_MODEL,
                            messages=messages_retry,
                            temperature=0,
                            response_format={"type": "json_object"},
                        )
                        if hasattr(resp2, "usage") and resp2.usage:
                            log(pr_num, "usage", f"tokens (retry): {resp2.usage.total_tokens}")
                        text2 = resp2.choices[0].message.content
                        try:
                            result = json.loads(text2)
                        except json.JSONDecodeError:
                            log(pr_num, "skip", "JSON parse failure after retry")
                            return None
                    else:
                        log(pr_num, "skip", "JSON parse failure")
                        return None
            else:
                result = text

            # Cache successful response
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            
            # Global token pacing
            time.sleep(3) 
            return result

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower():
                wait = 10
                m = re.search(r'Please try again in (\d+\.?\d*)s', err_str)
                if m:
                    wait = min(float(m.group(1)) + 1.0, 600)
                else:
                    wait = min(2 ** attempt * 2, 600)
                log(pr_num, "retry", f"429 rate limit, waiting {wait}s")
                time.sleep(wait)
                attempt += 1
                if attempt > 20: # hard limit just in case
                    return None
            else:
                log(pr_num, "error", f"LLM call failed: {err_str}")
                if attempt >= 2:
                    return None
                time.sleep(1)
                attempt += 1


# ---------------------------------------------------------------------------
# Hindsight wrapper
# ---------------------------------------------------------------------------
_hindsight_server = None
_hindsight_client = None


def get_hindsight():
    global _hindsight_server, _hindsight_client
    if _hindsight_client is not None:
        return _hindsight_client

    from hindsight_client import Hindsight

    kwargs = {"base_url": HINDSIGHT_BASE_URL}
    if HINDSIGHT_API_KEY:
        kwargs["api_key"] = HINDSIGHT_API_KEY
    elif "localhost" not in HINDSIGHT_BASE_URL and "127.0.0.1" not in HINDSIGHT_BASE_URL:
        raise ValueError("HINDSIGHT_API_KEY is required for non-local endpoints")

    _hindsight_client = Hindsight(**kwargs)
    
    try:
        _hindsight_client.create_bank(BANK_ID)
    except Exception as e:
        print(f"  Bank creation error (likely exists): {e}")
        
    return _hindsight_client


def _hindsight_retry_loop(func, *args, **kwargs):
    for attempt in range(4):
        try:
            res = func(*args, **kwargs)
            return res
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "402" in err_str or "403" in err_str:
                raise RuntimeError(f"Hindsight Auth/Billing Error: {err_str}")
            if "429" in err_str or "quota" in err_str.lower():
                # Amendment: stop immediately on 429 from Hindsight
                raise RuntimeError(f"quota_exhausted: {err_str}")
            if "50" in err_str or "timeout" in err_str.lower():
                if attempt == 3:
                    raise RuntimeError(f"Hindsight transient error limit reached: {err_str}")
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Hindsight unexpected error: {err_str}")








# ---------------------------------------------------------------------------
# Diff analysis helpers
# ---------------------------------------------------------------------------
def extract_touched_files(diff_text):
    """Extract file paths from a unified diff."""
    files = set()
    for line in diff_text.split("\n"):
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line.split("/", 1)[1] if "/" in line else ""
            if path and path != "/dev/null":
                files.add(path)
    return list(files)


def extract_functions(diff_text):
    """Extract function names from diff hunks."""
    functions = set()
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            m = re.search(r"def\s+(\w+)", line)
            if m:
                functions.add(m.group(1))
    return list(functions)


def extract_added_lines(diff_text):
    """Extract lines added in a diff."""
    added = []
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added)


def summarize_diff(pr):
    """Create a human-readable summary of what a PR does."""
    title = pr.get("title", "")
    message = pr.get("message", "")
    diff = pr.get("diff", "")
    files = extract_touched_files(diff)
    funcs = extract_functions(diff)

    summary = f"PR '{title}': {message}"
    if files:
        summary += f" (touches: {', '.join(files)})"
    if funcs:
        summary += f" (functions: {', '.join(funcs)})"
    return summary


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------
def step_recall(pr, hacks, pr_num):
    """Query Hindsight with touched files and semantic paraphrase."""
    diff = pr.get("diff", "")
    if not diff.strip():
        log(pr_num, "recall", "empty diff, skipping recall")
        return []

    files = extract_touched_files(diff)
    funcs = extract_functions(diff)
    comments = []

    # File/function-based recall
    if files or funcs:
        query_parts = []
        if files:
            query_parts.append(f"files: {', '.join(files)}")
        if funcs:
            query_parts.append(f"functions: {', '.join(funcs)}")
        file_query = "Code changes touching " + "; ".join(query_parts)
        log(pr_num, "recall", f"file query: {file_query[:80]}")
        recall_result = hindsight_recall(file_query)
        if recall_result:
            log(pr_num, "recall", f"file recall returned results")
            for hack in hacks:
                if hack["status"] != "open":
                    continue
                # Check if any recalled memory relates to this hack
                hack_path = hack.get("current_path", hack["path_at_add"])
                hack_func = hack.get("current_function", hack["function_at_add"])
                for f in files:
                    if f == hack_path or hack_func in (funcs or []):
                        comments.append({
                            "kind": "related_hack",
                            "hack_id": hack["id"],
                            "path": f,
                            "anchor_snippet": hack["anchor_snippet"],
                            "body_md": (
                                f"This PR touches code near a tracked workaround.\n\n"
                                f"**Hack {hack['id']}**: {hack['what']}\n"
                                f"- Why: {hack['why']}\n"
                                f"- Risk: {hack['risk']}\n"
                                f"- Revisit condition: {hack['revisit_condition']}\n"
                                f"- Location: `{hack_path}` in `{hack_func}`"
                            ),
                            "evidence_prs": [hack["pr_added"]],
                        })
                        log(pr_num, "recall", f"related_hack: {hack['id']} via file match")

    # Semantic paraphrase recall
    purpose = summarize_diff(pr)
    semantic_query = f"What workarounds or hacks relate to: {purpose}"
    log(pr_num, "recall", f"semantic query: {semantic_query[:80]}")
    semantic_result = hindsight_recall(semantic_query)
    if semantic_result:
        log(pr_num, "recall", f"semantic recall returned results")

    return comments


def step_classify(pr, pr_num):
    """Classify if PR introduces a workaround using Groq."""
    diff = pr.get("diff", "")
    if not diff.strip():
        log(pr_num, "classify", "empty diff, skipping")
        return None

    added = extract_added_lines(diff)
    files = extract_touched_files(diff)

    messages = [
        {"role": "system", "content": ONBOARDING_ENGINEER["system_prompt"]},
        {"role": "user", "content": f"""Analyze this pull request and determine if it introduces a workaround, hack, or temporary fix.

PR Title: {pr["title"]}
PR Message: {pr["message"]}
Files touched: {", ".join(files)}
Diff (added lines):
{added[:3000]}

Return a JSON object with these fields:
- is_workaround: boolean
- what: string describing the workaround (empty if not a workaround)
- why: string explaining why it exists (empty if not a workaround)
- risk: "low" or "medium" or "high"
- revisit_condition: plain-language description of the real-world condition that would make this safe to remove (empty if not a workaround)
- ticket_id: ticket ID if mentioned (null otherwise)
- anchor_snippet: the exact 1 to 3 code lines from the diff that implement the hack (empty if not a workaround)

A workaround is code that works around a limitation, bug, or constraint that is expected to be resolved in the future. Look for comments containing words like "hack", "workaround", "temporary", "remove when", "revisit", or code that explicitly mentions a condition for removal."""},
    ]

    result = call_llm(messages, pr_num=pr_num)
    if result:
        log(pr_num, "classify", f"is_workaround={result.get('is_workaround')}")
    return result


def step_resolve_check(pr, hacks, pr_num):
    """Check if this PR resolves any open hack. Reality Checker gates."""
    comments = []
    diff = pr.get("diff", "")
    message = pr.get("message", "")
    title = pr.get("title", "")
    closes_ticket = pr.get("closes_ticket")

    open_hacks = [h for h in hacks if h["status"] == "open"]
    if not open_hacks:
        return comments

    paths_str = ", ".join(extract_touched_files(diff))
    intent = title + " " + message
    recall_query = f"Which of the active workarounds does this PR resolve? Intent: {intent}, Paths: {paths_str}"
    recall_result = hindsight_recall(recall_query)
    recalled_text = str(recall_result)
    
    # Extract top 5 hack IDs from recall results
    matched_ids = []
    for match in re.finditer(r'(?:HACK-|PR #0*)(\d+)', recalled_text):
        hid = f"HACK-{int(match.group(1)):03d}"
        if hid not in matched_ids and any(h["id"] == hid for h in open_hacks):
            matched_ids.append(hid)
            if len(matched_ids) == 5:
                break
                
    # Fallback to checking up to 5 open hacks if recall string parsing failed
    if not matched_ids:
        matched_ids = [h["id"] for h in open_hacks][:5]

    for hack in open_hacks:
        if hack["id"] not in matched_ids:
            continue

        # SQL baseline: what a simple ticket_id JOIN would find
        sql_rows = []
        sql_query = f"SELECT * FROM hacks WHERE ticket_id = '{closes_ticket}' AND status = 'open'"
        if closes_ticket and hack.get("ticket_id") and closes_ticket == hack["ticket_id"]:
            sql_rows = [{"hack_id": hack["id"], "ticket_id": hack["ticket_id"]}]

        log(pr_num, "check", f"resolve-check for hack {hack['id']}")

        # Reality Checker gate
        checker_messages = [
            {"role": "system", "content": REALITY_CHECKER["system_prompt"]},
            {"role": "user", "content": f"""Evaluate whether this PR resolves the following workaround.

WORKAROUND:
- ID: {hack["id"]}
- What: {hack["what"]}
- Why: {hack["why"]}
- Revisit condition: {hack["revisit_condition"]}
- Anchor code: {hack["anchor_snippet"]}
- Ticket: {hack.get("ticket_id", "none")}

PR UNDER REVIEW:
- Title: {title}
- Message: {message}
- Closes ticket: {closes_ticket or "none"}
- Diff excerpt: {diff[:1500]}

Memory context (if any): {recalled_text[:500] if recall_result else "none"}

First argue AGAINST the match. Then decide.
Return JSON:
- verdict: "MATCH" or "NEEDS_WORK"
- confidence: float 0 to 1
- counter_arguments: list of strings (reasons this might NOT be a match)
- reasoning: string explaining your final judgment"""},
        ]

        checker = call_llm(checker_messages, pr_num=pr_num)
        if not checker:
            continue

        verdict = checker.get("verdict", "NEEDS_WORK")
        confidence = checker.get("confidence", 0)

        log(pr_num, "check", f"hack {hack['id']}: {verdict} (conf={confidence})")

        if verdict == "MATCH" and confidence >= 0.8:
            comments.append({
                "kind": "resolves",
                "hack_id": hack["id"],
                "path": hack.get("current_path", hack["path_at_add"]),
                "anchor_snippet": hack["anchor_snippet"],
                "body_md": (
                    f"This PR appears to resolve a tracked workaround.\n\n"
                    f"**Hack {hack['id']}**: {hack['what']}\n"
                    f"- Revisit condition: {hack['revisit_condition']}\n"
                    f"- Reasoning: {checker.get('reasoning', '')}\n"
                ),
                "evidence_prs": [hack["pr_added"], pr_num],
                "checker": checker,
                "sql_baseline": {
                    "query": sql_query,
                    "rows": sql_rows,
                },
            })
            log(pr_num, "check", f"RESOLVED: hack {hack['id']}")

    return comments


def step_reflect(pr, hacks, classification, pr_num):
    """Cross-hack reflect: check if 3+ open workarounds share a root cause."""
    comments = []
    open_hacks = [h for h in hacks if h["status"] == "open"]

    if len(open_hacks) < 3:
        log(pr_num, "reflect", f"only {len(open_hacks)} open hacks, skipping reflect")
        return comments

    recall_query = classification.get("why", "")
    recall_result = hindsight_recall(recall_query, top_k=8)
    
    similar_ids = []
    if recall_result and hasattr(recall_result, 'results'):
        for res in recall_result.results:
            doc_id = res.document_id
            if doc_id and doc_id != classification.get("id") and doc_id not in similar_ids:
                similar_ids.append(doc_id)
                
    # Filter only open hacks
    open_similar_ids = [hid for hid in similar_ids if any(h["id"] == hid for h in open_hacks)]
    
    log(pr_num, "reflect_gate", f"query: {recall_query[:80]}...")
    log(pr_num, "reflect_gate", f"recall hit IDs: {similar_ids}")
    log(pr_num, "reflect_gate", f"survivors after open filter: {open_similar_ids}")
    
    if len(open_similar_ids) < 2:
        log(pr_num, "reflect_gate", f"returned IDs: []")
        log(pr_num, "reflect", f"only {len(open_similar_ids)} open similar hacks, skipping reflect")
        return comments

    # One Groq call to ask which share same external root cause
    cand_text = "\n".join([f"ID: {h['id']}, What: {h['what']}, Why: {h['why']}" for h in open_hacks if h['id'] in open_similar_ids])
    messages = [
        {"role": "system", "content": "You analyze workarounds to find shared external root causes. Return JSON: {'shared_ids': ['HACK-xxx', ...]}"},
        {"role": "user", "content": f"New hack:\nWhat: {classification.get('what')}\nWhy: {classification.get('why')}\n\nCandidates:\n{cand_text}\n\nWhich of the candidates share the same external root cause as the new hack? Exclude ones with different root causes (e.g., different vendors/APIs)."}
    ]
    
    gate_result = call_llm(messages, pr_num=pr_num, json_mode=True)
    shared_ids = gate_result.get("shared_ids", []) if gate_result else []
    
    log(pr_num, "reflect_gate", f"returned IDs: {shared_ids}")
    
    if len(shared_ids) < 2:
        log(pr_num, "reflect", f"only {len(shared_ids)} shared root cause hacks, skipping reflect")
        return comments
        
    similar_open_hacks = len(shared_ids)

    # Build context for reflect
    hacks_desc = "\n".join(
        f"- Hack {h['id']}: {h['what']} (why: {h['why']}, condition: {h['revisit_condition']})"
        for h in open_hacks if h["id"] in shared_ids or h["id"] == classification.get("id")
    )

    reflect_query = (
        f"Do three or more of these independent open workarounds share an "
        f"underlying root cause? If so, what is it and what single fix would "
        f"address them all?\n\n{hacks_desc}"
    )

    log(pr_num, "reflect", "running cross-hack reflect")
    reflect_result = hindsight_reflect(reflect_query)

    # Also ask LLM for structured output
    reflect_messages = [
        {"role": "system", "content": ONBOARDING_ENGINEER["system_prompt"]},
        {"role": "user", "content": f"""Analyze these open workarounds and determine if three or more share an underlying root cause.

Open workarounds:
{hacks_desc}

Current PR adds: {classification.get("what", "")} because {classification.get("why", "")}

Memory synthesis: {str(reflect_result)[:1000] if reflect_result else "none"}

Return JSON:
- shares_root_cause: boolean
- root_cause: string describing the shared root cause (empty if false)
- hack_ids: list of hack IDs that share this root cause
- summary: one-line summary
- proposal: one concrete consolidation proposal (e.g. a single wrapper or abstraction that would replace all the individual workarounds)"""},
    ]

    result = call_llm(reflect_messages, pr_num=pr_num)
    if result and result.get("shares_root_cause") and len(result.get("hack_ids", [])) >= 3:
        comments.append({
            "kind": "root_cause",
            "path": None,
            "anchor_snippet": None,
            "body_md": (
                f"Three or more workarounds share an underlying root cause.\n\n"
                f"**Root cause**: {result['root_cause']}\n"
                f"**Suggestion**: {result['proposal']}\n"
                f"**Affected hacks**: {', '.join(result['hack_ids'])}"
            ),
            "evidence_prs": [h["pr_added"] for h in open_hacks if h["id"] in result.get("hack_ids", [])],
            "suggestion": {
                "summary": result.get("summary", ""),
                "proposal": result.get("proposal", ""),
                "hack_ids": result.get("hack_ids", []),
            },
        })
        log(pr_num, "reflect", f"root_cause found: {result.get('hack_ids')}")

    return comments


# ---------------------------------------------------------------------------
# Hack management
# ---------------------------------------------------------------------------
def create_hack(pr, classification, pr_num):
    """Create a new hack entry from a classification."""
    hack_id = f"HACK-{pr_num:03d}"

    # Determine path and function from diff
    diff = pr.get("diff", "")
    files = extract_touched_files(diff)
    funcs = extract_functions(diff)

    path = files[0] if files else "unknown"
    function = funcs[0] if funcs else "unknown"

    # Build natural-language note for Hindsight
    note = (
        f"Workaround added in PR #{pr_num} titled '{pr['title']}' by {pr['author']}. "
        f"{classification['what']}. "
        f"This exists because {classification['why']}. "
        f"It should be removed when {classification['revisit_condition']}. "
        f"Risk level: {classification['risk']}. "
        f"Located in {path}, function {function}."
    )

    return {
        "id": hack_id,
        "pr_added": pr_num,
        "path_at_add": path,
        "function_at_add": function,
        "current_path": path,
        "current_function": function,
        "what": classification.get("what", ""),
        "why": classification.get("why", ""),
        "risk": classification.get("risk", "medium"),
        "revisit_condition": classification.get("revisit_condition", ""),
        "ticket_id": classification.get("ticket_id"),
        "anchor_snippet": classification.get("anchor_snippet", ""),
        "status": "open",
        "status_since_pr": pr_num,
        "location_by_pr": {str(pr_num): {"path": path, "function": function}},
        "note_text": note,
    }


def update_hack_location(hack, pr, pr_num):
    """After a rename, update the hack's current path and function."""
    diff = pr.get("diff", "")
    files_after = pr.get("files_after", {})

    # Check if anchor snippet appears in any new file
    snippet = hack["anchor_snippet"]
    if not snippet:
        return False

    for fpath, content in files_after.items():
        if _snippet_in(snippet, content) and fpath != hack["current_path"]:
            old_path = hack["current_path"]
            hack["current_path"] = fpath
            # Try to find the function name
            for line in content.split("\n"):
                if "def " in line:
                    m = re.search(r"def\s+(\w+)", line)
                    if m:
                        # Check if this function contains the snippet
                        func_name = m.group(1)
                        func_start = content.index(line)
                        # Simple: if snippet is after this def and before next def
                        remaining = content[func_start:]
                        if _snippet_in(snippet, remaining.split("def ")[0] if "def " in remaining[1:] else remaining):
                            hack["current_function"] = func_name
                            break
            hack["location_by_pr"][str(pr_num)] = {
                "path": hack["current_path"],
                "function": hack["current_function"],
            }
            log(pr_num, "retain", f"hack {hack['id']} moved: {old_path} -> {fpath}")
            return True
    return False

def check_hack_retired(hack, pr, pr_num):
    """Check if a PR deletes the hack's anchor snippet."""
    diff = pr.get("diff", "")
    snippet = hack["anchor_snippet"]
    if not snippet:
        return False

    files_after = pr.get("files_after", {})
    current_path = hack.get("current_path", hack["path_at_add"])
    if current_path in files_after:
        content = files_after[current_path]
        if not _snippet_in(snippet, content):
            hack["status"] = "retired"
            hack["status_since_pr"] = pr_num
            log(pr_num, "retain", f"hack {hack['id']} retired (anchor removed)")
            return True
    return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(limit=None, resume_from=None):
    with open(COMMITS_FILE, "r", encoding="utf-8") as f:
        commits = json.load(f)

    hacks = []
    pr_results = []
    comment_id_counter = 0

    for i, pr in enumerate(commits):
        pr_num = pr["pr_number"]

        if resume_from and pr_num < resume_from:
            continue
        if limit and i >= limit:
            break

        log(pr_num, "start", f"processing PR #{pr_num}: {pr['title']}")

        pr_comments = []
        pr_log = []
        skipped = False
        tag = ""
        diff = pr.get("diff", "")

        try:
            # --- Step 1: Recall ---
            recall_comments = step_recall(pr, hacks, pr_num)
            pr_comments.extend(recall_comments)
            if recall_comments:
                tag = tag or ""

            # --- Step 2: Classify ---
            classification = step_classify(pr, pr_num)

            if classification and classification.get("is_workaround"):
                tag = "HACK"

                # --- Step 4 (before merge): Cross-hack reflect ---
                # Check if this would be the 3rd+ hack
                new_hack = create_hack(pr, classification, pr_num)
                temp_hacks = hacks + [new_hack]
                reflect_comments = step_reflect(pr, temp_hacks, classification, pr_num)
                pr_comments.extend(reflect_comments)

            # --- Step 3: Resolve-check on EVERY PR ---
            resolve_comments = step_resolve_check(pr, hacks, pr_num)
            pr_comments.extend(resolve_comments)
            if resolve_comments:
                tag = tag or "FIX"

            # Check for renames/moves
            if not tag:
                # Check if any hack's anchor moved
                for hack in hacks:
                    if hack["status"] == "open" and update_hack_location(hack, pr, pr_num):
                        tag = "MOVE"
                        # Emit related_hack comment for the move
                        pr_comments.append({
                            "kind": "related_hack",
                            "hack_id": hack["id"],
                            "path": hack["current_path"],
                            "anchor_snippet": hack["anchor_snippet"],
                            "body_md": (
                                f"This PR moves a tracked workaround to a new location.\n\n"
                                f"**Hack {hack['id']}**: {hack['what']}\n"
                                f"- Previous location: `{hack['path_at_add']}` in `{hack['function_at_add']}`\n"
                                f"- New location: `{hack['current_path']}` in `{hack['current_function']}`"
                            ),
                            "evidence_prs": [hack["pr_added"]],
                        })

            # --- Merge: retain and update ---
            # Retain workaround note
            if classification and classification.get("is_workaround"):
                new_hack = create_hack(pr, classification, pr_num)
                hacks.append(new_hack)
                note = new_hack["note_text"]
                hindsight_retain(note, document_id=new_hack["id"])
                log(pr_num, "retain", f"retained hack {new_hack['id']}")

            # Update hack statuses after resolves
            for comment in resolve_comments:
                hack_id = comment.get("hack_id")
                for hack in hacks:
                    if hack["id"] == hack_id:
                        hack["status"] = "condition_met"
                        hack["status_since_pr"] = pr_num

            # Check retirements
            for hack in hacks:
                if hack["status"] in ("open", "condition_met"):
                    check_hack_retired(hack, pr, pr_num)
                    if hack["status"] == "retired":
                        pr_comments.append({
                            "kind": "retired",
                            "hack_id": hack["id"],
                            "path": hack.get("current_path"),
                            "anchor_snippet": hack["anchor_snippet"],
                            "body_md": (
                                f"Workaround removed.\n\n"
                                f"**Hack {hack['id']}**: {hack['what']}\n"
                                f"The anchor code has been deleted from the codebase."
                            ),
                            "evidence_prs": [hack["pr_added"], pr_num],
                        })

            # Update location tracking for all hacks at this PR
            for hack in hacks:
                if hack["status"] != "retired":
                    hack["location_by_pr"][str(pr_num)] = {
                        "path": hack["current_path"],
                        "function": hack["current_function"],
                    }

        except Exception as e:
            log(pr_num, "skip", f"error: {e}")
            skipped = True

        # Assign comment IDs
        for c in pr_comments:
            comment_id_counter += 1
            c["id"] = f"CMT-{comment_id_counter:03d}"

        # Determine files_after containing tracked hacks
        files_with_hacks = {}
        for hack in hacks:
            if hack["status"] != "retired":
                hp = hack.get("current_path", hack["path_at_add"])
                if hp in pr.get("files_after", {}):
                    files_with_hacks[hp] = pr["files_after"][hp]

        pr_results.append({
            "pr": pr_num,
            "title": pr["title"],
            "author": pr["author"],
            "date": pr["date"],
            "branch": pr["branch"],
            "tag": tag,
            "diff": diff,
            "files_after": files_with_hacks,
            "log": [{"kind": entry["kind"], "text": entry["text"]}
                    for entry in _log_lines if entry["pr"] == pr_num],
            "skipped": skipped,
            "comments": pr_comments,
        })

        log(pr_num, "done", f"tag={tag}, comments={len(pr_comments)}")

    # Build final results
    results = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": GROQ_MODEL,
            "bank_id": BANK_ID,
        },
        "prs": pr_results,
        "hacks": [
            {
                "id": h["id"],
                "pr_added": h["pr_added"],
                "path_at_add": h["path_at_add"],
                "function_at_add": h["function_at_add"],
                "what": h["what"],
                "why": h["why"],
                "risk": h["risk"],
                "revisit_condition": h["revisit_condition"],
                "ticket_id": h["ticket_id"],
                "anchor_snippet": h["anchor_snippet"],
                "status": h["status"],
                "status_since_pr": h["status_since_pr"],
                "location_by_pr": h["location_by_pr"],
                "note_text": h["note_text"],
            }
            for h in hacks
        ],
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Update docs with BANK_ID
    for filename in ["README.md", "MEMORY_USAGE.md"]:
        p = DATA_DIR.parent / filename
        if p.exists():
            c = p.read_text(encoding="utf-8")
            c = re.sub(r'BANK_ID_PLACEHOLDER|payments-service-[a-f0-9]+', BANK_ID, c)
            p.write_text(c, encoding="utf-8")


    print(f"\nResults written to {RESULTS_FILE}")
    print(f"  {len(pr_results)} PRs processed")
    print(f"  {len(hacks)} hacks tracked")
    print(f"  {comment_id_counter} comments generated")
    return results


def shutdown_hindsight():
    global _hindsight_server
    if _hindsight_server:
        try:
            _hindsight_server.stop()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CodeMemory ingestion pipeline")
    parser.add_argument("--limit", type=int, help="Process only first N PRs")
    parser.add_argument("--resume", type=int, help="Resume from PR number")
    args = parser.parse_args()

    try:
        results = run_pipeline(limit=args.limit, resume_from=args.resume)
    finally:
        shutdown_hindsight()
