# CodeMemory

Remembers why engineering workarounds exist and when they can be removed.

## What it does

CodeMemory tracks workarounds (hacks, temporary fixes, tech debt) across a codebase. It speaks to developers at three moments:

1. **Editor**: hovering a tracked hack shows what it is, why it exists, who added it, risk level, and the plain-language condition for removal.
2. **Pull request**: before merge, a review comment surfaces when a PR touches an area with an open hack, or when a PR may satisfy a hack's removal condition even though it shares no ticket, file, or wording with the hack.
3. **Suggestion**: when a PR would add a third workaround with the same underlying cause, a non-blocking suggestion proposes a root-cause fix.

All output is advisory. Nothing blocks a merge.

## Why it needs memory

| Capability | SQL / ticket-ID join | Hindsight memory |
|---|---|---|
| Find hack by exact file path | Yes | Yes |
| Find hack by ticket ID | Yes | Yes |
| Find hack after file rename | No | Yes (recall by anchor snippet) |
| Find hack across paraphrase | No | Yes (semantic recall) |
| Resolve undeclared relationship | No | Yes (recall by intent, not ID) |
| Cross-hack root-cause synthesis | No | Yes (reflect over bank) |

Flag-once-and-store fails exactly when the resolving signal was never predicted at write-time and shares no ID with the thing it resolves. Almost nobody writes "revisit when ticket 482 closes". They write "remove once Stripe fixes their rate limiting", with no ticket at all.

## Personas

Two LLM prompt dispositions are used:

- **Reality Checker**: gate persona for resolution matching. Defaults to NEEDS_WORK and must argue against a match before accepting it. Requires overwhelming evidence.
- **Codebase Onboarding Engineer**: tone persona for all user-facing text. Plain, factual, assumes zero context.

Adapted from the disposition framing described in github.com/vectorize-io/self-driving-agents (disposition style reuse only, no code dependency).

## Data methodology

The sample repository is a small Flask payments service (6 source files, each under 40 lines). The commit history is synthetic: authored specifically for this demo, replayed into a real git repository with correct dates, authors, and diffs.

26 PRs span February to August 2026, with 11 plot PRs carrying the story and 15 noise PRs (logging, tests, dependency bumps, docs). Four fictional authors with distinct commit message styles.

To be clear: the repo and history are authored by us to demonstrate the mechanism, since we had no proprietary codebase in this timeframe.

## Setup

```bash
# 1. Install dependencies
pip install -r codememory/requirements.txt

# 2. Build the sample repository (creates sample_repo/ and data/commits.json)
python codememory/build_repo.py



# 4. Run the web demo
cd codememory && python -m http.server 8080
```

Open http://localhost:8080 in a browser (1440x900 recommended).

To run the full pipeline with Hindsight and Groq (requires API key):

```bash
cp codememory/.env.example codememory/.env
# Edit .env and add your GROQ_API_KEY
python codememory/ingest.py
```

Note: The pipeline uses the `openai/gpt-oss-20b` model for all operations (both direct Groq calls and Hindsight memory operations) to ensure it stays well within daily token quotas while providing fast responses.

## Surfaces: real vs simulated

| Surface | Status |
|---|---|
| Pipeline (ingest.py) | Real. Runs Hindsight embedded + Groq to classify, recall, resolve-check, and reflect. |
| Baked results (results.json) | Real pipeline output, pre-computed. |
| Web demo (PR view, editor, hacks ledger) | Simulated. Static HTML/JS reading results.json. |
| VS Code extension | Real. Reads results.json and shows hover cards in sample_repo files. |
| GitHub Action (pr_comment.py) | Simulated. Prints what the bot would post, does not call GitHub API. |

## Running tests

```bash
python -m pytest codememory/tests/verify.py -v
```

## Honest limitations

- Resolution events are rare per hack. A workaround may exist for months before a resolving signal appears.
- Semantic recall depends on the quality of the retain note. Poorly described workarounds are harder to match.
- The Reality Checker gate can produce false negatives on genuinely resolving PRs if the evidence is indirect.
- Root-cause synthesis requires at least three open hacks to trigger.

## Roadmap

- Ingest vendor changelogs and release notes (e.g. Stripe API changelog) as candidate resolving events
- Real GitHub Action integration for automated PR review
- Support for multiple memory banks across services

## References

<!-- TODO: verify each statistic before submission -->
- Stripe reports that 42% of developer time is spent on maintenance and tech debt (Source: Stripe Developer Coefficient, 2018)
- CAST estimates technical debt costs \$3.61 per line of code (Source: CAST Research Labs)
- SonarSource estimates technical debt costs \$306K per year per 1M lines of code (Source: SonarSource)
- Gartner estimates 40% of IT budgets go to maintenance (Source: Gartner)

## Memory

This project uses [Hindsight](https://github.com/vectorize-io/hindsight) by Vectorize.io for semantic memory. See [MEMORY_USAGE.md](MEMORY_USAGE.md) for detailed usage documentation.
