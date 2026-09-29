# Hindsight Memory Usage

CodeMemory uses [Hindsight](https://github.com/vectorize-io/hindsight) by Vectorize.io as its semantic memory layer. This document explains how the three memory operations (retain, recall, reflect) are used in the pipeline, with real examples from the demo data.

## Setup

Hindsight runs in embedded mode (no separate server needed):

```python
from hindsight import HindsightServer
from hindsight_client import Hindsight

server = HindsightServer(
    llm_provider="groq",
    llm_model="openai/gpt-oss-120b",
    llm_api_key=os.environ["GROQ_API_KEY"],
)
server.start()

client = Hindsight(base_url=server.get_base_url())
```

All data is stored in a single memory bank: `payments-service`.

## Retain

When a PR introducing a workaround is merged, a natural-language note is stored in the bank. The note describes what, why, risk, and the condition for removal.

Notes are always plain prose, never JSON dumps. This is intentional: memory recall works on natural language, not structured data.

**Example: HACK-006 (fixed retry delay)**

```
Workaround added in PR #6 titled 'use fixed retry delay for charge attempts'
by Priya Sharma. Fixed 3-second retry delay instead of exponential backoff
for Stripe charges. This exists because Stripe's batch endpoint throttles
under sustained load and exponential backoff causes downstream timeouts.
It should be removed when Stripe's batch endpoint stops throttling under load.
Risk level: medium. Located in billing/retry.py, function charge_customer.
```

## Recall

On each new PR, Hindsight is queried twice:

1. **File/function recall**: query with the touched file paths and function names. This surfaces exact matches and matches after renames.
2. **Semantic recall**: query with a paraphrase of the PR's purpose. This surfaces related hacks even when the wording is different.

**Example: rename detection (PR #17)**

After `billing/retry.py` is renamed to `billing/stripe_retry.py` and `charge_customer` becomes `submit_charge`, querying with:

```
Code changes touching billing/stripe_retry.py, function submit_charge
```

recalls the HACK-006 memory because the anchor snippet text is still present in the new file. A SQL join on file path would miss this.

**Example: undeclared relationship (PR #24)**

PR #24 upgrades stripe-sdk to 4.2 and switches to a batched charge API. It shares no ticket, file path, or wording with HACK-006 (the fixed retry delay). But querying with:

```
Upgrade stripe sdk to 4.2. The new version has a proper batched charge
API with server-side rate limiting. Should resolve throughput issues.
```

recalls HACK-006's note because "server-side rate limiting" and "batch endpoint stops throttling" are semantically related. A SQL query returns 0 rows because there is no shared ticket ID.

## Reflect

When a PR adds a third workaround, the pipeline runs reflect over the entire bank to find shared root causes.

**Example: root-cause synthesis (PR #22)**

After PR #22 adds the third Stripe-related hack, reflect is called with:

```
Do three or more of these independent open workarounds share an underlying
root cause?

- HACK-006: Fixed retry delay (Stripe throttling)
- HACK-012: Tax rate caching (tax provider slow)
- HACK-015: Stripe timeout increase (Stripe timeouts)
- HACK-022: Batch charge verification (Stripe inconsistent results)
```

Reflect identifies that HACK-006, HACK-015, and HACK-022 all stem from Stripe API instability under load, while HACK-012 involves a different vendor. It proposes a single Stripe client wrapper as a consolidation.

## Why memory, not SQL

The core value of memory over a database comes from three capabilities:

1. **Recall across paraphrase and rename**: after a file rename, the hack's location is found by searching for its anchor snippet text across the codebase, not by matching file paths.

2. **Resolving undeclared relationships**: PR #24 resolves HACK-006 despite sharing no ticket ID, file path, or keyword. Semantic recall bridges the gap.

3. **Cross-hack root-cause synthesis**: reflect synthesizes across multiple independent memories to identify patterns that no individual query would surface.

These three cases are where "flag once and store in a database" breaks down. The easy cases (ticket ID joins, exact file matches) work fine with SQL and are not the point.


Note: CodeMemory uses Hindsight Cloud for semantic memory. Direct LLM calls (classify/checker) use Groq's qwen/qwen3.8-27b. Results come from a real ingest.py run.
