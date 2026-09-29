"""
Authored PR history for the payments-service sample repository.

Each entry is one PR (one commit). files maps path -> full file text after
the PR (None means delete). Plot PRs carry the story; noise PRs add realism.
"""

# ---------------------------------------------------------------------------
# Source file templates -- small, runnable Flask payment service
# ---------------------------------------------------------------------------

CHECKOUT_V1 = """\
from flask import Flask, request, jsonify
import stripe

app = Flask(__name__)

@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json()
    charge = stripe.Charge.create(
        amount=data["amount"],
        currency=data.get("currency", "usd"),
        source=data["source"],
    )
    return jsonify({"charge_id": charge.id, "status": charge.status})
"""

CONFIG_V1 = """\
import os

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
TAX_PROVIDER_URL = os.environ.get("TAX_PROVIDER_URL", "https://tax.example.com")
TAX_CACHE_TTL = int(os.environ.get("TAX_CACHE_TTL", "300"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///payments.db")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
"""

WEBHOOKS_V1 = """\
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)

def handle_webhook(app):
    @app.route("/webhooks/stripe", methods=["POST"])
    def stripe_webhook():
        payload = request.get_json()
        event_type = payload.get("type", "")
        event_id = payload.get("id", "")
        logger.info("received webhook %s: %s", event_id, event_type)
        if event_type == "charge.succeeded":
            _process_charge(payload["data"]["object"])
        return jsonify({"received": True})

    def _process_charge(charge):
        logger.info("processing charge %s", charge["id"])
"""

BILLING_RETRY_V1 = """\
import stripe
import time
import logging

logger = logging.getLogger(__name__)

def charge_customer(customer_id, amount, currency="usd"):
    \"\"\"Attempt a charge with basic retry logic.\"\"\"
    for attempt in range(3):
        try:
            return stripe.Charge.create(
                customer=customer_id,
                amount=amount,
                currency=currency,
            )
        except stripe.error.RateLimitError:
            wait = 2 ** attempt
            logger.warning("rate limited, retrying in %ds", wait)
            time.sleep(wait)
    raise RuntimeError("charge failed after retries")
"""

TAX_V1 = """\
import requests
import logging
from config import TAX_PROVIDER_URL

logger = logging.getLogger(__name__)

def get_tax_rate(country_code, product_type="digital"):
    \"\"\"Fetch current tax rate from provider.\"\"\"
    resp = requests.get(
        f"{TAX_PROVIDER_URL}/rates",
        params={"country": country_code, "type": product_type},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["rate"]
"""

INVOICES_V1 = """\
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_invoice(customer_id, line_items, tax_rate=0.0):
    \"\"\"Build an invoice dict from line items.\"\"\"
    subtotal = sum(item["amount"] for item in line_items)
    tax = round(subtotal * tax_rate, 2)
    return {
        "customer_id": customer_id,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
        "issued_at": datetime.utcnow().isoformat(),
        "status": "pending",
    }
"""

# -- After T1: webhook dedup hack
WEBHOOKS_T1 = """\
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)

# HACK: skip duplicate webhook deliveries using an in-memory set.
# Stripe sometimes sends the same event twice within a few seconds.
# Revisit when PAY-212 adds idempotency at the database layer.
_seen_events = set()

def handle_webhook(app):
    @app.route("/webhooks/stripe", methods=["POST"])
    def stripe_webhook():
        payload = request.get_json()
        event_type = payload.get("type", "")
        event_id = payload.get("id", "")
        if event_id in _seen_events:
            logger.info("skipping duplicate event %s", event_id)
            return jsonify({"received": True, "duplicate": True})
        _seen_events.add(event_id)
        logger.info("received webhook %s: %s", event_id, event_type)
        if event_type == "charge.succeeded":
            _process_charge(payload["data"]["object"])
        return jsonify({"received": True})

    def _process_charge(charge):
        logger.info("processing charge %s", charge["id"])
"""

# -- After S1: 3s fixed retry delay for Stripe rate limiting
BILLING_RETRY_S1 = """\
import stripe
import time
import logging

logger = logging.getLogger(__name__)

def charge_customer(customer_id, amount, currency="usd"):
    \"\"\"Attempt a charge with retry logic.\"\"\"
    for attempt in range(3):
        try:
            return stripe.Charge.create(
                customer=customer_id,
                amount=amount,
                currency=currency,
            )
        except stripe.error.RateLimitError:
            # Workaround: fixed 3-second delay instead of exponential backoff.
            # Stripe's batch endpoint throttles under sustained load and
            # exponential backoff causes timeouts downstream.
            # Remove once Stripe's batch endpoint stops throttling under load.
            wait = 3
            logger.warning("rate limited on charge, waiting %ds (fixed)", wait)
            time.sleep(wait)
    raise RuntimeError("charge failed after retries")
"""

# -- After T2: second ticket-tied hack (PAY-240)
CHECKOUT_T2 = """\
from flask import Flask, request, jsonify
import stripe
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json()
    amount = data["amount"]
    # HACK: cap single charge to 50000 cents due to a downstream ledger
    # overflow bug. Revisit when PAY-240 migrates ledger to bigint columns.
    if amount > 50000:
        logger.warning("capping charge amount from %d to 50000", amount)
        amount = 50000
    charge = stripe.Charge.create(
        amount=amount,
        currency=data.get("currency", "usd"),
        source=data["source"],
    )
    return jsonify({"charge_id": charge.id, "status": charge.status})
"""

# -- After easy-case resolver: T1 resolved, webhook dedup removed
WEBHOOKS_RESOLVED = """\
from flask import request, jsonify
import logging
from db import get_db

logger = logging.getLogger(__name__)

def handle_webhook(app):
    @app.route("/webhooks/stripe", methods=["POST"])
    def stripe_webhook():
        payload = request.get_json()
        event_type = payload.get("type", "")
        event_id = payload.get("id", "")
        db = get_db()
        if db.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
        ).fetchone():
            logger.info("skipping duplicate event %s (db)", event_id)
            return jsonify({"received": True, "duplicate": True})
        db.execute("INSERT INTO processed_events (event_id) VALUES (?)", (event_id,))
        db.commit()
        logger.info("received webhook %s: %s", event_id, event_type)
        if event_type == "charge.succeeded":
            _process_charge(payload["data"]["object"])
        return jsonify({"received": True})

    def _process_charge(charge):
        logger.info("processing charge %s", charge["id"])
"""

# -- After S2: tax rate caching hack
TAX_S2 = """\
import requests
import time
import logging
from config import TAX_PROVIDER_URL, TAX_CACHE_TTL

logger = logging.getLogger(__name__)

# Workaround: cache tax rates in memory because the tax provider API
# responds slowly (p95 over 2 seconds). Remove when the provider
# brings latency reliably below 200ms.
_tax_cache = {}
_cache_times = {}

def get_tax_rate(country_code, product_type="digital"):
    \"\"\"Fetch current tax rate, with caching.\"\"\"
    cache_key = f"{country_code}:{product_type}"
    now = time.time()
    if cache_key in _tax_cache and (now - _cache_times[cache_key]) < TAX_CACHE_TTL:
        return _tax_cache[cache_key]
    resp = requests.get(
        f"{TAX_PROVIDER_URL}/rates",
        params={"country": country_code, "type": product_type},
        timeout=5,
    )
    resp.raise_for_status()
    rate = resp.json()["rate"]
    _tax_cache[cache_key] = rate
    _cache_times[cache_key] = now
    return rate
"""

# -- After R2: raise Stripe timeout and cap concurrency
CONFIG_R2 = """\
import os

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
TAX_PROVIDER_URL = os.environ.get("TAX_PROVIDER_URL", "https://tax.example.com")
TAX_CACHE_TTL = int(os.environ.get("TAX_CACHE_TTL", "300"))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///payments.db")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# Workaround: raised timeout from default 10s to 45s and cap concurrency
# at 4 because Stripe times out under concurrent load.
# Remove when Stripe stabilizes response times for batch operations.
STRIPE_TIMEOUT = int(os.environ.get("STRIPE_TIMEOUT", "45"))
STRIPE_MAX_CONCURRENT = int(os.environ.get("STRIPE_MAX_CONCURRENT", "4"))
"""

CHECKOUT_R2 = """\
from flask import Flask, request, jsonify
import stripe
import logging
from config import STRIPE_TIMEOUT, STRIPE_MAX_CONCURRENT
import threading

app = Flask(__name__)
logger = logging.getLogger(__name__)
_charge_semaphore = threading.Semaphore(STRIPE_MAX_CONCURRENT)

@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json()
    amount = data["amount"]
    if amount > 50000:
        logger.warning("capping charge amount from %d to 50000", amount)
        amount = 50000
    with _charge_semaphore:
        charge = stripe.Charge.create(
            amount=amount,
            currency=data.get("currency", "usd"),
            source=data["source"],
            timeout=STRIPE_TIMEOUT,
        )
    return jsonify({"charge_id": charge.id, "status": charge.status})
"""

# -- After MOVE: rename billing/retry.py -> billing/stripe_retry.py
BILLING_STRIPE_RETRY_MOVE = """\
import stripe
import time
import logging

logger = logging.getLogger(__name__)

def submit_charge(customer_id, amount, currency="usd"):
    \"\"\"Submit a charge with retry logic.\"\"\"
    for attempt in range(3):
        try:
            return stripe.Charge.create(
                customer=customer_id,
                amount=amount,
                currency=currency,
            )
        except stripe.error.RateLimitError:
            # Workaround: fixed 3-second delay instead of exponential backoff.
            # Stripe's batch endpoint throttles under sustained load and
            # exponential backoff causes timeouts downstream.
            # Remove once Stripe's batch endpoint stops throttling under load.
            wait = 3
            logger.warning("rate limited on charge, waiting %ds (fixed)", wait)
            time.sleep(wait)
    raise RuntimeError("charge failed after retries")
"""

# -- After R3: batch charge verification hack
INVOICES_R3 = """\
import logging
import stripe
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_invoice(customer_id, line_items, tax_rate=0.0):
    \"\"\"Build an invoice dict from line items.\"\"\"
    subtotal = sum(item["amount"] for item in line_items)
    tax = round(subtotal * tax_rate, 2)
    return {
        "customer_id": customer_id,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
        "issued_at": datetime.utcnow().isoformat(),
        "status": "pending",
    }

def batch_charge_and_invoice(customer_id, line_items, tax_rate=0.0):
    \"\"\"Charge for all items then build an invoice.

    Workaround: after batch charges, re-verify each total individually
    and fall back to per-charge mode because Stripe's batch API returns
    inconsistent totals under load.
    Remove when Stripe's batch charge API returns consistent totals.
    \"\"\"
    total = sum(item["amount"] for item in line_items)
    try:
        batch = stripe.Charge.create(amount=total, customer=customer_id)
        # Verify: re-fetch and compare
        fetched = stripe.Charge.retrieve(batch.id)
        if fetched.amount != total:
            logger.warning("batch total mismatch, falling back to per-charge")
            for item in line_items:
                stripe.Charge.create(amount=item["amount"], customer=customer_id)
    except stripe.error.APIError:
        logger.warning("batch charge failed, falling back to per-charge")
        for item in line_items:
            stripe.Charge.create(amount=item["amount"], customer=customer_id)
    return generate_invoice(customer_id, line_items, tax_rate)
"""

# -- After RESOLVER: stripe-sdk 4.2 with batched charge API
BILLING_STRIPE_RETRY_RESOLVER = """\
import stripe
import time
import logging

logger = logging.getLogger(__name__)

def submit_charge(customer_id, amount, currency="usd"):
    \"\"\"Submit a charge using the batched charge API.\"\"\"
    for attempt in range(3):
        try:
            return stripe.Charge.create(
                customer=customer_id,
                amount=amount,
                currency=currency,
            )
        except stripe.error.RateLimitError:
            # Workaround: fixed 3-second delay instead of exponential backoff.
            # Stripe's batch endpoint throttles under sustained load and
            # exponential backoff causes timeouts downstream.
            # Remove once Stripe's batch endpoint stops throttling under load.
            wait = 3
            logger.warning("rate limited on charge, waiting %ds (fixed)", wait)
            time.sleep(wait)
    raise RuntimeError("charge failed after retries")
"""

# -- After CLEANUP: S1 delay removed
BILLING_STRIPE_RETRY_CLEANUP = """\
import stripe
import logging

logger = logging.getLogger(__name__)

def submit_charge(customer_id, amount, currency="usd"):
    \"\"\"Submit a charge using the batched charge API.

    The fixed retry delay workaround has been removed now that
    stripe-sdk 4.2 handles rate limiting properly.
    \"\"\"
    return stripe.Charge.create(
        customer=customer_id,
        amount=amount,
        currency=currency,
    )
"""

# -- DB module added in the easy-case resolver PR
DB_MODULE = """\
import sqlite3
import os
from config import DATABASE_URL

_connection = None

def get_db():
    global _connection
    if _connection is None:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        _connection = sqlite3.connect(db_path)
        _connection.execute(
            "CREATE TABLE IF NOT EXISTS processed_events "
            "(event_id TEXT PRIMARY KEY, processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    return _connection
"""

# -- requirements.txt for sample_repo
REQUIREMENTS = """\
flask==3.0.0
stripe==4.2.0
requests==2.31.0
"""

# ---------------------------------------------------------------------------
# PR timeline
# ---------------------------------------------------------------------------

PRS = [
    # --- PR 1: initial scaffolding
    {
        "pr_number": 1,
        "title": "Initial payments service scaffolding",
        "branch": "init-payments",
        "author": "Priya Sharma",
        "date": "2026-02-03T09:14:00",
        "message": "set up flask app with checkout endpoint, billing retry, tax lookup, webhooks, invoices, and config",
        "files": {
            "checkout.py": CHECKOUT_V1,
            "config.py": CONFIG_V1,
            "webhooks.py": WEBHOOKS_V1,
            "billing/retry.py": BILLING_RETRY_V1,
            "tax.py": TAX_V1,
            "invoices.py": INVOICES_V1,
            "requirements.txt": REQUIREMENTS.replace("4.2.0", "3.8.0"),
        },
        "closes_ticket": None,
    },
    # --- PR 2: noise -- add logging config
    {
        "pr_number": 2,
        "title": "configure structured logging",
        "branch": "logging-setup",
        "author": "Marcus Chen",
        "date": "2026-02-10T14:32:00",
        "message": "added json logging handler, log level from config",
        "files": {
            "logging_config.py": """\
import logging
import json
from config import LOG_LEVEL

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.module,
        })

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(getattr(logging, LOG_LEVEL))
""",
        },
        "closes_ticket": None,
    },
    # --- PR 3: noise -- add health check
    {
        "pr_number": 3,
        "title": "feat: add health check endpoint",
        "branch": "feat/health-check",
        "author": "Aisha Okafor",
        "date": "2026-02-18T11:05:00",
        "message": "feat: add /health endpoint returning service status and version",
        "files": {
            "health.py": """\
from flask import jsonify
import os

VERSION = os.environ.get("SERVICE_VERSION", "0.1.0")

def register_health(app):
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": VERSION})
""",
        },
        "closes_ticket": None,
    },
    # --- PR 4 (T1): webhook duplicate skip hack
    {
        "pr_number": 4,
        "title": "fix duplicate webhook processing",
        "branch": "fix-webhook-dupes",
        "author": "Marcus Chen",
        "date": "2026-03-02T16:41:00",
        "message": "skip duplicate webhook events using in-memory set. not ideal but stops the double-charge issue until PAY-212 lands",
        "files": {
            "webhooks.py": WEBHOOKS_T1,
        },
        "closes_ticket": None,
    },
    # --- PR 5: noise -- add tests
    {
        "pr_number": 5,
        "title": "add unit tests for invoice generation",
        "branch": "tests-invoices",
        "author": "Priya Sharma",
        "date": "2026-03-08T10:20:00",
        "message": "basic test coverage for generate_invoice, edge cases for zero amounts",
        "files": {
            "tests/test_invoices.py": """\
import unittest
from invoices import generate_invoice

class TestInvoice(unittest.TestCase):
    def test_basic_invoice(self):
        items = [{"amount": 1000}, {"amount": 2000}]
        inv = generate_invoice("cust_1", items, tax_rate=0.1)
        self.assertEqual(inv["subtotal"], 3000)
        self.assertEqual(inv["tax"], 300.0)
        self.assertEqual(inv["total"], 3300.0)

    def test_zero_amount(self):
        inv = generate_invoice("cust_2", [], tax_rate=0.2)
        self.assertEqual(inv["total"], 0)

if __name__ == "__main__":
    unittest.main()
""",
        },
        "closes_ticket": None,
    },
    # --- PR 6 (S1): fixed 3s retry delay -- Stripe rate limiting
    {
        "pr_number": 6,
        "title": "use fixed retry delay for charge attempts",
        "branch": "fix-retry-delay",
        "author": "Priya Sharma",
        "date": "2026-03-19T08:55:00",
        "message": "switch to fixed 3s delay between retries. exponential backoff was causing downstream timeouts because stripe's batch endpoint throttles under sustained load. not a great fix but keeps charges flowing",
        "files": {
            "billing/retry.py": BILLING_RETRY_S1,
        },
        "closes_ticket": None,
    },
    # --- PR 7: noise -- update readme
    {
        "pr_number": 7,
        "title": "docs: update README with setup instructions",
        "branch": "docs/readme-update",
        "author": "Aisha Okafor",
        "date": "2026-03-25T13:10:00",
        "message": "docs: add local dev setup, env vars, and stripe test key instructions",
        "files": {
            "README.md": """\
# Payments Service

Local development setup for the payments API.

## Setup

1. Copy `.env.example` to `.env`
2. Set STRIPE_API_KEY to your test key
3. Run `pip install -r requirements.txt`
4. Run `flask run`

## Environment Variables

- STRIPE_API_KEY: Stripe secret key
- TAX_PROVIDER_URL: Tax rate API base URL
- DATABASE_URL: SQLite connection string
""",
        },
        "closes_ticket": None,
    },
    # --- PR 8 (T2): ledger overflow cap hack
    {
        "pr_number": 8,
        "title": "cap single charge amount at 50000",
        "branch": "fix-ledger-overflow",
        "author": "Marcus Chen",
        "date": "2026-04-07T15:30:00",
        "message": "cap checkout amount to prevent ledger overflow. the downstream ledger uses int columns and overflows above 50000 cents. hack until PAY-240 migrates to bigint",
        "files": {
            "checkout.py": CHECKOUT_T2,
        },
        "closes_ticket": None,
    },
    # --- PR 9: noise -- fix typo in logging
    {
        "pr_number": 9,
        "title": "fix typo in webhook log message",
        "branch": "fix-typo",
        "author": "James Park",
        "date": "2026-04-11T09:45:00",
        "message": "fixed typo: recieved -> received in webhook handler",
        "files": {
            "webhooks.py": WEBHOOKS_T1,  # same content, the "typo" was in a noise line
        },
        "closes_ticket": None,
    },
    # --- PR 10 (easy-case resolver): closes PAY-212, resolves T1
    {
        "pr_number": 10,
        "title": "feat: database-backed event idempotency",
        "branch": "feat/idempotent-webhooks",
        "author": "Aisha Okafor",
        "date": "2026-04-22T10:15:00",
        "message": "feat: replace in-memory duplicate check with database-backed idempotency.\n\nStores processed event IDs in SQLite. The in-memory set was unreliable\nacross restarts and multiple workers.",
        "files": {
            "webhooks.py": WEBHOOKS_RESOLVED,
            "db.py": DB_MODULE,
        },
        "closes_ticket": "PAY-212",
    },
    # --- PR 11: noise -- add request validation
    {
        "pr_number": 11,
        "title": "validate checkout request body",
        "branch": "validate-checkout",
        "author": "Priya Sharma",
        "date": "2026-04-28T14:00:00",
        "message": "add basic validation for checkout payload fields, return 400 on missing amount or source",
        "files": {},  # just touches checkout.py with same content + minor validation
        "closes_ticket": None,
    },
    # --- PR 12 (S2): tax rate caching hack
    {
        "pr_number": 12,
        "title": "cache tax provider responses",
        "branch": "cache-tax-rates",
        "author": "James Park",
        "date": "2026-05-06T11:30:00",
        "message": "cache tax rates in memory, ttl from config. the tax provider api is too slow for real-time checkout. will remove if they get their latency under control",
        "files": {
            "tax.py": TAX_S2,
        },
        "closes_ticket": None,
    },
    # --- PR 13: noise -- dependency bump (non-stripe)
    {
        "pr_number": 13,
        "title": "bump requests to 2.32.0",
        "branch": "bump-requests",
        "author": "Priya Sharma",
        "date": "2026-05-12T08:50:00",
        "message": "update requests from 2.31.0 to 2.32.0 for security patch",
        "files": {
            "requirements.txt": REQUIREMENTS.replace("2.31.0", "2.32.0").replace("4.2.0", "3.8.0"),
        },
        "closes_ticket": None,
    },
    # --- PR 14: noise -- add error handler
    {
        "pr_number": 14,
        "title": "feat: add global error handler",
        "branch": "feat/error-handler",
        "author": "Aisha Okafor",
        "date": "2026-05-20T16:15:00",
        "message": "feat: register global error handlers for 400, 404, 500 with JSON responses",
        "files": {
            "errors.py": """\
from flask import jsonify
import logging

logger = logging.getLogger(__name__)

def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "bad request", "message": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("internal server error")
        return jsonify({"error": "internal server error"}), 500
""",
        },
        "closes_ticket": None,
    },
    # --- PR 15 (R2): raise Stripe timeout and cap concurrency
    {
        "pr_number": 15,
        "title": "increase stripe timeout and limit concurrency",
        "branch": "stripe-timeout-fix",
        "author": "James Park",
        "date": "2026-05-28T09:20:00",
        "message": "raise stripe client timeout to 45s and cap concurrent charges at 4. stripe times out under load and concurrent requests make it worse. not a real fix but keeps the service from falling over",
        "files": {
            "config.py": CONFIG_R2,
            "checkout.py": CHECKOUT_R2,
        },
        "closes_ticket": None,
    },
    # --- PR 16: noise -- add metrics
    {
        "pr_number": 16,
        "title": "add basic metrics counters",
        "branch": "add-metrics",
        "author": "Marcus Chen",
        "date": "2026-06-03T14:45:00",
        "message": "track charge success/failure counts and webhook processing times",
        "files": {
            "metrics.py": """\
import time
import logging

logger = logging.getLogger(__name__)

_counters = {}

def increment(name, value=1):
    _counters[name] = _counters.get(name, 0) + value

def get_counts():
    return dict(_counters)

class Timer:
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        self.start = time.time()
        return self
    def __exit__(self, *args):
        elapsed = time.time() - self.start
        logger.info("%s took %.3fs", self.name, elapsed)
""",
        },
        "closes_ticket": None,
    },
    # --- PR 17 (MOVE): rename billing/retry.py -> billing/stripe_retry.py
    {
        "pr_number": 17,
        "title": "reorganize billing modules",
        "branch": "reorganize-billing",
        "author": "Priya Sharma",
        "date": "2026-06-10T10:30:00",
        "message": "reorganize billing modules for clarity. moved retry logic to stripe_retry and renamed charge_customer to submit_charge",
        "files": {
            "billing/retry.py": None,  # delete
            "billing/stripe_retry.py": BILLING_STRIPE_RETRY_MOVE,
        },
        "closes_ticket": None,
    },
    # --- PR 18: noise -- add env example
    {
        "pr_number": 18,
        "title": "add .env.example file",
        "branch": "env-example",
        "author": "Marcus Chen",
        "date": "2026-06-15T11:20:00",
        "message": "add example env file so new devs know what to configure",
        "files": {
            ".env.example": """\
STRIPE_API_KEY=sk_test_xxx
TAX_PROVIDER_URL=https://tax.example.com
DATABASE_URL=sqlite:///payments.db
LOG_LEVEL=INFO
STRIPE_TIMEOUT=45
STRIPE_MAX_CONCURRENT=4
""",
        },
        "closes_ticket": None,
    },
    # --- PR 19 (near-miss noise): stripe-sdk 4.0.3 bump, logging only
    {
        "pr_number": 19,
        "title": "bump stripe-sdk to 4.0.3",
        "branch": "bump-stripe-403",
        "author": "James Park",
        "date": "2026-06-22T08:10:00",
        "message": "upgrade stripe sdk to 4.0.3, only changes are improved error logging and deprecation notices",
        "files": {
            "requirements.txt": REQUIREMENTS.replace("2.31.0", "2.32.0").replace("4.2.0", "4.0.3"),
        },
        "closes_ticket": None,
    },
    # --- PR 20: noise -- add webhook signature verification
    {
        "pr_number": 20,
        "title": "feat: verify webhook signatures",
        "branch": "feat/webhook-sig",
        "author": "Aisha Okafor",
        "date": "2026-07-01T13:40:00",
        "message": "feat: add Stripe webhook signature verification using endpoint secret",
        "files": {},
        "closes_ticket": None,
    },
    # --- PR 21: noise -- add retry tests
    {
        "pr_number": 21,
        "title": "add tests for charge retry logic",
        "branch": "test-retry",
        "author": "Priya Sharma",
        "date": "2026-07-08T09:30:00",
        "message": "test retry behavior and rate limit handling in billing module",
        "files": {
            "tests/test_retry.py": """\
import unittest
from unittest.mock import patch, MagicMock
from billing.stripe_retry import submit_charge

class TestRetry(unittest.TestCase):
    @patch("billing.stripe_retry.stripe.Charge.create")
    def test_successful_charge(self, mock_create):
        mock_create.return_value = MagicMock(id="ch_123")
        result = submit_charge("cust_1", 5000)
        self.assertEqual(result.id, "ch_123")

if __name__ == "__main__":
    unittest.main()
""",
        },
        "closes_ticket": None,
    },
    # --- PR 22 (R3): batch charge verification hack (third Stripe hack)
    {
        "pr_number": 22,
        "title": "add batch charge verification and fallback",
        "branch": "batch-charge-verify",
        "author": "Marcus Chen",
        "date": "2026-07-18T15:55:00",
        "message": "re-verify totals after batch charges and fall back to per-charge if they do not match. stripe's batch api returns inconsistent results and we have seen mismatches in production. ugly but necessary until stripe fixes it",
        "files": {
            "invoices.py": INVOICES_R3,
        },
        "closes_ticket": None,
    },
    # --- PR 23: noise -- docs update
    {
        "pr_number": 23,
        "title": "docs: document batch charging flow",
        "branch": "docs/batch-charging",
        "author": "Aisha Okafor",
        "date": "2026-07-25T10:10:00",
        "message": "docs: add sequence diagram and notes for the batch charge and invoice flow",
        "files": {},
        "closes_ticket": None,
    },
    # --- PR 24 (RESOLVER): stripe-sdk 4.2 + batched charge API
    {
        "pr_number": 24,
        "title": "upgrade to stripe-sdk 4.2 and use batched charge API",
        "branch": "stripe-sdk-42",
        "author": "James Park",
        "date": "2026-08-05T14:20:00",
        "message": "upgrade stripe sdk to 4.2. the new version has a proper batched charge api with server-side rate limiting. switched checkout to use it. should resolve the throughput issues we have been having",
        "files": {
            "requirements.txt": REQUIREMENTS.replace("2.31.0", "2.32.0"),
            "billing/stripe_retry.py": BILLING_STRIPE_RETRY_RESOLVER,
        },
        "closes_ticket": None,
    },
    # --- PR 25: noise -- cleanup unused imports
    {
        "pr_number": 25,
        "title": "remove unused imports",
        "branch": "cleanup-imports",
        "author": "Priya Sharma",
        "date": "2026-08-12T09:00:00",
        "message": "ran autoflake across the codebase, removed unused imports",
        "files": {},
        "closes_ticket": None,
    },
    # --- PR 26 (CLEANUP): remove S1 delay
    {
        "pr_number": 26,
        "title": "remove fixed retry delay workaround",
        "branch": "remove-retry-delay",
        "author": "Priya Sharma",
        "date": "2026-08-20T11:45:00",
        "message": "the fixed 3s retry delay is no longer needed after the stripe sdk upgrade. stripe-sdk 4.2 handles rate limiting properly now. removing the workaround",
        "files": {
            "billing/stripe_retry.py": BILLING_STRIPE_RETRY_CLEANUP,
        },
        "closes_ticket": None,
    },
]
