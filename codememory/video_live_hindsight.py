"""Live Hindsight recording helper for the CodeMemory demo.

Uses the project's real Hindsight wrappers from ingest.py. This does not
modify results.json; it only starts an embedded Hindsight instance, writes
a few demo memories, and shows live recall/reflect output in the terminal.

Run from the CodeMemory project root:
    python video_live_hindsight.py

Requires the same .env configuration used by ingest.py.
"""

from ingest import hindsight_retain, hindsight_recall, hindsight_reflect


MEMORIES = [
    (
        "HACK-006",
        "Workaround added in PR #6. Fixed 3-second retry delay instead of exponential backoff for Stripe charges. This exists because Stripe's batch endpoint throttles under sustained load and exponential backoff causes downstream timeouts. Remove when Stripe's batch endpoint stops throttling under load. Risk level: medium. Located in billing/retry.py, function charge_customer.",
    ),
    (
        "HACK-015",
        "Workaround added in PR #15. Stripe client timeout is increased to 45 seconds and concurrent charge requests are limited to four. This exists because Stripe requests time out under load. Remove when Stripe remains stable without the extended timeout and concurrency cap. Risk level: medium. Located in config.py.",
    ),
    (
        "HACK-022",
        "Workaround added in PR #22. Batch charge totals are re-verified and the flow falls back to individual charges when totals mismatch or the API errors. This exists because Stripe's batch charge API returns inconsistent totals under load. Remove when the batch charge API returns consistent totals. Risk level: medium. Located in invoices.py, function batch_charge_and_invoice.",
    ),
]


def main() -> None:
    print("\n=== LIVE HINDSIGHT DEMO ===\n")
    print("1) RETAIN: storing workaround history in memory\n")
    for hack_id, note in MEMORIES:
        hindsight_retain(note)
        print(f"retained {hack_id}")

    print("\n2) RECALL: finding history by meaning, not by exact wording\n")
    query = (
        "What workaround relates to Stripe batch charge instability under load, "
        "especially retry behavior or inconsistent batch totals?"
    )
    result = hindsight_recall(query)
    print(result)

    print("\n3) REFLECT: synthesizing a pattern across memories\n")
    reflect_query = (
        "What common underlying problem appears across these workarounds, "
        "and what single engineering change could reduce them?"
    )
    reflection = hindsight_reflect(reflect_query)
    print(reflection)


if __name__ == "__main__":
    main()
