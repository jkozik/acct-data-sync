"""Shared Plaid API client setup, built from .env."""
import json
import os
import sys
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api

load_dotenv()

PLAID_ENV = os.environ["PLAID_ENV"]
PLAID_CLIENT_ID = os.environ["PLAID_CLIENT_ID"]
PLAID_PRODUCTS = os.environ.get("PLAID_PRODUCTS", "transactions").split(",")
PLAID_COUNTRY_CODES = os.environ.get("PLAID_COUNTRY_CODES", "US").split(",")

# Sandbox and production use different secrets; pick the one matching PLAID_ENV.
if PLAID_ENV == "sandbox":
    PLAID_SECRET = os.environ["PLAID_SECRET_SANDBOX"]
    _host = plaid.Environment.Sandbox
elif PLAID_ENV == "production":
    PLAID_SECRET = os.environ["PLAID_SECRET"]
    _host = plaid.Environment.Production
else:
    raise ValueError(f"Unsupported PLAID_ENV: {PLAID_ENV!r} (expected 'sandbox' or 'production')")

configuration = plaid.Configuration(
    host=_host,
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    },
)
api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)


PLAID_ERROR_HINTS = {
    "ITEM_LOGIN_REQUIRED": "Re-run Plaid Link update mode for this item (link_app.py, port 5001) to re-authenticate.",
    "ADDITIONAL_CONSENT_REQUIRED": "Re-run Plaid Link update mode for this item (link_app.py, port 5001), granting the missing product.",
    "ITEM_NOT_FOUND": "The stored access token no longer maps to a live Item -- check tokens.json, or the Item may have been removed in the Plaid dashboard.",
    "INVALID_ACCESS_TOKEN": "The stored access token is invalid -- check tokens.json for corruption, or re-link via link_app.py.",
    "PRODUCT_NOT_READY": "Plaid is still processing this product for this Item (e.g. shortly after linking) -- wait a few minutes and retry.",
    # error_type RATE_LIMIT_EXCEEDED, HTTP 429 -- these are the specific
    # error_codes Plaid actually sends (error_type itself is not the code).
    # Most are per-Item/per-minute caps this tool's normal usage (a handful of
    # manual triggers a day) shouldn't come close to -- if one fires, it's far
    # more likely a retry loop or accidental double-click than real load.
    "TRIAL_CONNECTION_LIMIT": "You've hit the Plaid Trial plan's Item cap (10 Items) -- this is NOT transient and won't clear by waiting/retrying. Remove an old Item or upgrade off Trial to add a new one.",
    "CREDITS_EXHAUSTED": "Your free API call allocation is used up for this period -- check the Plaid dashboard's billing/usage page for options. Also not transient.",
    "RATE_LIMIT": "Generic Plaid rate limit / suspected-abuse throttle -- back off and retry; if this keeps happening, check for a retry loop in the code.",
    "ACCOUNTS_LIMIT": "Hit /accounts/get's per-Item limit (15/min) -- should be far above this tool's normal call volume; check for an accidental retry loop.",
    "ACCOUNTS_BALANCE_GET_LIMIT": "Hit /accounts/balance/get's per-client limit -- back off and retry.",
    "BALANCE_LIMIT": "Hit /accounts/balance/get's per-Item limit (5/min, 30/hr) -- this is the tightest limit this tool touches; back off well beyond a minute before retrying.",
    "TRANSACTIONS_LIMIT": "Hit /transactions/get's per-Item limit (30/min) -- back off and retry.",
    "TRANSACTIONS_SYNC_LIMIT": "Hit /transactions/sync's per-Item limit (50/min) -- back off and retry; check for a retry loop.",
    "TRANSACTIONS_REFRESH_LIMIT": "Hit /transactions/refresh's strict daily cap -- this tool doesn't call refresh directly, so this would be unexpected; needs a long backoff (hours, not minutes).",
    "ITEM_GET_LIMIT": "Hit /item/get's per-Item limit (15/min) -- back off and retry.",
    "INSTITUTION_RATE_LIMIT": "Throttling from the bank itself (via Plaid), not Plaid's own limit -- back off; may need to wait longer than a normal Plaid rate limit.",
}
DEFAULT_PLAID_ERROR_HINT = (
    "Unrecognized Plaid error_code -- see https://plaid.com/docs/errors/ for this "
    "error_type/error_code, and quote plaid_request_id if you contact Plaid support."
)
DEFAULT_RATE_LIMIT_HINT = (
    "Plaid rate limit hit (error_type RATE_LIMIT_EXCEEDED) but this specific error_code "
    "isn't one we've mapped a hint for -- see https://plaid.com/docs/errors/rate-limit-exceeded/ "
    "for what it means. This tool's normal usage (a handful of manual triggers a day) is well "
    "under Plaid's published limits, so this is more likely a retry loop than real load."
)


def describe_plaid_error(exc):
    """Parse a plaid.ApiException's body into a structured dict, with a
    troubleshooting hint for known error codes. Used by export_api.py to build
    both HTTP error responses and log entries -- and by CLI scripts (via
    print_friendly_error_and_exit) for a readable terminal message.
    """
    try:
        body = json.loads(exc.body)
    except (TypeError, ValueError):
        body = {}
    error_type = body.get("error_type", "UNKNOWN")
    error_code = body.get("error_code")

    if error_code in PLAID_ERROR_HINTS:
        hint = PLAID_ERROR_HINTS[error_code]
    elif error_type == "RATE_LIMIT_EXCEEDED":
        hint = DEFAULT_RATE_LIMIT_HINT
    else:
        hint = DEFAULT_PLAID_ERROR_HINT

    return {
        "source": "plaid",
        "error_type": error_type,
        "error_code": error_code or "UNKNOWN",
        "error_message": body.get("error_message", str(exc)),
        "display_message": body.get("display_message"),
        "plaid_request_id": body.get("request_id"),
        "hint": hint,
    }


def print_friendly_error_and_exit(exc):
    """CLI-only: print describe_plaid_error()'s info and exit(1).

    Never call this from export_api.py -- exiting the process there would
    silently kill the whole long-running API instead of returning an HTTP
    error to the caller.
    """
    info = describe_plaid_error(exc)
    print(
        f"\nERROR from Plaid: {info['error_type']}/{info['error_code']}: {info['error_message']}\n"
        f"{info['hint']}\n",
        file=sys.stderr,
    )
    sys.exit(1)


def raise_friendly_if_login_required(exc):
    """Re-raise a plaid.ApiException unchanged.

    Historically this printed a friendly message and exited on
    ITEM_LOGIN_REQUIRED, but that's unsafe to call from a long-running server
    (export_api.py) -- exiting there would silently kill the whole API rather
    than return an HTTP error. CLI scripts now get their friendly message via
    print_friendly_error_and_exit() in their own main(); this function is kept
    as a pass-through so its existing call sites (accounts.py, balances.py,
    liabilities.py, sync_transactions.py) don't need to change.
    """
    raise exc
