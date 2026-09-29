import os
import sys
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load env before importing hindsight_client if needed
load_dotenv(Path('c:/Users/Lenovo/Desktop/CodeMemory/codememory/.env'))

import hindsight_client

def run_diagnostics():
    base_url = os.environ.get("HINDSIGHT_BASE_URL", "")
    api_key = os.environ.get("HINDSIGHT_API_KEY", "")
    
    if not api_key:
        print("Error: HINDSIGHT_API_KEY is not set.")
        return

    client = hindsight_client.Hindsight(base_url=base_url, api_key=api_key)
    bank_id = "diagnose-bank-1234"
    
    print(f"Creating bank: {bank_id}")
    try:
        client.create_bank(bank_id=bank_id)
    except Exception as e:
        print(f"Bank creation output (might already exist): {e}")

    print("\n--- Retain Note 1 ---")
    resp1 = client.retain(
        bank_id=bank_id,
        content="Stripe rate limiting workaround added in submit_charge. We wait 3 seconds before retrying.",
        document_id="DIAG-001"
    )
    print("Retain response 1:")
    print(resp1)

    print("\n--- Retain Note 2 ---")
    resp2 = client.retain(
        bank_id=bank_id,
        content="Stripe rate limiting workaround added in process_payment. We retry up to 5 times.",
        document_id="DIAG-002"
    )
    print("Retain response 2:")
    print(resp2)
    
    async def wait_for_op(op_id):
        print(f"Waiting for operation {op_id} to complete...")
        for i in range(30):
            try:
                op = await client.operations.get_operation_status(bank_id, op_id)
                print(f"  Poll {i}: {op.status}")
                if op.status.lower() in ("completed", "done", "success"):
                    return
                if op.status.lower() in ("failed", "error"):
                    print("  Operation failed:", getattr(op, 'error_message', 'Unknown'))
                    return
            except Exception as e:
                print(f"  Poll error: {e}")
            await asyncio.sleep(2)
        print("  Timeout waiting for operation")

    var_async = getattr(resp2, 'var_async', False)
    op_id = getattr(resp2, 'operation_id', None)
    if var_async and op_id:
        asyncio.run(wait_for_op(op_id))

    def do_recall(label):
        print(f"\n--- Recall: {label} ---")
        try:
            recall_resp = client.recall(bank_id=bank_id, query="Stripe rate limiting workaround", top_k=5)
            results = getattr(recall_resp, 'results', []) or []
            print(f"Raw result count: {len(results)}")
            
            if results:
                first = results[0]
                print(f"First result fields:")
                print(f"  document_id: {getattr(first, 'document_id', None)}")
                print(f"  metadata: {getattr(first, 'metadata', None)}")
                print(f"  text: {getattr(first, 'text', None)}")
                
                # Ingest mapping logic
                print("Ingest.py mapping logic:")
                matched_ids = []
                for res in results:
                    doc_id = getattr(res, 'document_id', None)
                    if doc_id and doc_id.startswith("DIAG-"):
                        if doc_id not in matched_ids:
                            matched_ids.append(doc_id)
                            if len(matched_ids) == 5:
                                break
                print(f"Matched IDs: {matched_ids}")
            else:
                print("No results returned.")
        except Exception as e:
            print("Recall error:", e)

    do_recall("Immediately")
    print("Waiting 10s...")
    time.sleep(10)
    do_recall("After 10s")
    print("Waiting 20s...")
    time.sleep(20)
    do_recall("After 30s")
    print("Waiting 30s...")
    time.sleep(30)
    do_recall("After 60s")

if __name__ == "__main__":
    run_diagnostics()
