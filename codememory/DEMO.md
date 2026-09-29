# Demo Script (90 seconds)

Follow the guided run or present manually. Open http://localhost:8080 at 1440x900.

## Steps

### 1. Introduce (10s)
"CodeMemory remembers why workarounds exist and tells you when they can be removed."

Click through the PR timeline to show the ledger filling up.

### 2. S1: workaround introduced (15s)
Navigate to PR #6 (use fixed retry delay for charge attempts).

Show the diff: a fixed 3-second delay replaces exponential backoff because Stripe throttles under load. No ticket. The revisit condition is plain language: "Remove once Stripe's batch endpoint stops throttling under load."

Click Merge. Note "Retained to memory" in the agent log.

Switch to Editor view. The hover card appears on `charge_customer`, showing what, why, risk, and the revisit condition.

### 3. Rename survives (10s)
Navigate to PR #17 (reorganize billing modules).

The review thread shows a `related_hack` comment: CodeMemory tracked the hack to its new location after the rename.

Switch to Editor view. The hover card now appears on `submit_charge` in `billing/stripe_retry.py`.

### 4. Resolver with no shared ticket (20s)
Navigate to PR #24 (upgrade to stripe-sdk 4.2).

The review thread shows a `resolves` comment for HACK-006. Point out:
- No shared ticket ID
- No shared file path (different file)
- No shared wording

Show the SQL baseline: "0 rows (no shared ticket)". A database join would miss this.

Show the Reality Checker output: verdict MATCH, confidence 88%, with counter-arguments it considered before accepting.

### 5. Root cause suggestion (15s)
Navigate to PR #22 (batch charge verification).

The review thread shows a `root_cause` comment: three Stripe hacks share an underlying cause. The suggestion proposes a single Stripe client wrapper.

Point out: HACK-012 (tax caching) is excluded because it involves a different vendor.

### 6. Cleanup (10s)
Navigate to PR #26. HACK-006 is marked retired.

The hacks ledger shows the status change. The workaround's lifecycle is complete: introduced, tracked through a rename, resolved by an unrelated PR, and retired when the code is removed.

### 7. Method drawer (10s)
Open Method. Show the memory-vs-SQL table. Read the judge defense sentence.

## Q&A Answers

**Why not a database?**
SQL joins on ticket IDs and file paths handle the easy cases. Memory handles the hard cases: renamed files, paraphrased conditions, and unrelated PRs that happen to resolve an old workaround. The demo shows both: PR #10 resolves HACK-004 via a ticket ID (the easy case), and PR #24 resolves HACK-006 with no shared identifier (the hard case).

**Is the data real?**
The repo and history are authored by us to demonstrate the mechanism, since we had no proprietary codebase in this timeframe. The pipeline code is real and runs against the synthetic data.

**How does this compare to CodeScene?**
CodeScene shows where knowledge risk concentrates via git authorship. It cannot say why a line exists or whether the condition that justified it has been resolved elsewhere. We provide the full retain-recall-reflect loop with semantic resolution.

**Would teams pay for this?**
<!-- TODO: verify before submission -->
Stripe reports 42% of developer time goes to maintenance (Source: Stripe, 2018). If a team spends 2 hours per sprint tracking down whether an old workaround is still needed, that time is directly addressable.

## Backup video steps

If the live demo fails, present the screenshots in order:
1. PR #6 merged, editor hover card
2. PR #17 related_hack comment, renamed hover
3. PR #24 resolves comment with empty SQL baseline
4. PR #22 root_cause suggestion
5. PR #26 retired status
6. Method drawer
