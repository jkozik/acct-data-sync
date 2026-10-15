"""
REST-ish trigger API for the Plaid export scripts, so an export can be kicked
off remotely (from a Windows PowerShell curl command) one account and one
action at a time, instead of running the CLI scripts by hand on dell1.

Endpoints:
    POST /exports/transactions/<account>
        Runs the activity-CSV export for one account. The bookkeeping
        software still finds the file itself via its "most recent file in
        this folder" convention, so the response just reports success/failure.

    POST /exports/balance/<account>
        Fetches currentBalance/lastStatementBalance, writes the same JSON
        snapshot file as before into PlaidBalances/, AND returns the numbers
        directly in the response body -- so a PowerShell script can build a
        clipboard-ready journal entry from one curl call instead of a
        trigger-then-fetch pair.

    GET /health
        No Plaid calls -- just reports, per account, whether its export
        directory exists and whether a stored access token is present. Meant
        to be hit first after moving this to a new host, to tell a migration
        problem apart from a Plaid problem before you even try a real export.

<account> is one of: 101, 301, 302, 304 -- the bookkeeping software's own
account numbers, not Plaid's internal login label or mask.

Status codes:
    200 - success.
    404 - the account key isn't recognized, the action isn't supported for
          that account (e.g. no balance export for 101/checking), or an expected
          local resource is missing (export directory, stored access token).
          That last case is deliberate: if this ever gets moved to another
          server and the websiteexports mount or tokens.json didn't come
          along, this is what should surface, not a generic 500.
    502 - Plaid itself returned an error. The response body carries Plaid's
          own error_type/error_code/error_message/plaid_request_id plus a
          troubleshooting hint -- see plaid_client.describe_plaid_error().
    500 - anything else unexpected (a bug here, not Plaid's fault).

Every request is also logged as one JSON line to logs/export_api.log,
including a full traceback for 500s.

Run with:  .venv/bin/python export_api.py
"""
import os
import json
import datetime
import traceback

import plaid
from flask import Flask, jsonify

from tokens import get_access_token
from accounts import get_account_id_by_mask
from balances import get_current_balance
from liabilities import get_last_statement_balance
from sync_transactions import fetch_all_transactions
from plaid_client import describe_plaid_error

from formatters.chase_checking import write_chase_checking_csv
from formatters.chase_card_301 import write_chase_card_301_csv
from formatters.chase_card_302 import write_chase_card_302_csv
from formatters.citi_card_304 import write_citi_card_304_csv
from formatters.balance_snapshot import write_balance_snapshot

BALANCE_OUTPUT_DIR = "/home/nf/websiteexports/PlaidBalances"
LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "export_api.log")

# current_balance is only meaningful for 101/checking (used to anchor its
# running Balance column); the card writers take it but ignore it, so every
# account can be called with the same (posted, current_balance, output_path) shape.
ACCOUNTS = {
    "101": {
        "label": "chase_household_login",
        "mask": "1018",
        "csv_dir": "/home/nf/websiteexports/Chase101Export",
        "csv_prefix": "Chase1018_Activity_Plaid",
        "write_csv": lambda posted, current_balance, path: write_chase_checking_csv(posted, current_balance, path),
        "supports_balance": False,
    },
    "301": {
        "label": "chase_household_login",
        "mask": "1818",
        "csv_dir": "/home/nf/websiteexports/Chase301Export",
        "csv_prefix": "Chase1818_Activity_Plaid",
        "write_csv": lambda posted, current_balance, path: write_chase_card_301_csv(posted, path),
        "supports_balance": True,
        "balance_filename": "Chase1818_Balance_Plaid.json",
    },
    "302": {
        "label": "chase_household_login",
        "mask": "4803",
        "csv_dir": "/home/nf/websiteexports/Chase302Export",
        "csv_prefix": "Chase4803_Activity_Plaid",
        "write_csv": lambda posted, current_balance, path: write_chase_card_302_csv(posted, path),
        "supports_balance": True,
        "balance_filename": "Chase4803_Balance_Plaid.json",
    },
    "304": {
        "label": "citi_universal_card",
        "mask": "3166",
        "csv_dir": "/home/nf/websiteexports/UniversalCard304Export",
        "csv_prefix": "Citi3166_Activity_Plaid",
        "write_csv": lambda posted, current_balance, path: write_citi_card_304_csv(posted, path),
        "supports_balance": True,
        "balance_filename": "Citi3166_Balance_Plaid.json",
    },
}

app = Flask(__name__)


def _log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    line = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"), **record}
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(line, default=str) + "\n")


def _respond(status_code, body, account, action):
    _log({"account": account, "action": action, "status_code": status_code, **body})
    return jsonify(body), status_code


def _not_found(message, account, action, hint=None):
    body = {"status": "error", "source": "client", "error_message": message}
    if hint:
        body["hint"] = hint
    return _respond(404, body, account, action)


def _plaid_error(exc, account, action):
    body = {"status": "error", **describe_plaid_error(exc)}
    return _respond(502, body, account, action)


def _internal_error(exc, account, action):
    body = {
        "status": "error",
        "source": "internal",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    _log({"account": account, "action": action, "status_code": 500,
          "traceback": traceback.format_exc(), **body})
    return jsonify(body), 500


def _lookup_account(account, action):
    """Look up ACCOUNTS[account], or a ready-to-return 404 response."""
    cfg = ACCOUNTS.get(account)
    if cfg is None:
        return None, _not_found(
            f"Unknown account key {account!r}. Valid keys: {', '.join(sorted(ACCOUNTS))}.",
            account, action,
        )
    return cfg, None


def _get_access_token_or_404(label, account, action):
    try:
        return get_access_token(label), None
    except KeyError as e:
        return None, _not_found(
            str(e), account, action,
            hint="This often means tokens.json wasn't carried over during a server "
                 "migration, or this account was never linked via link_app.py.",
        )


@app.route("/exports/transactions/<account>", methods=["POST"])
def export_transactions(account):
    cfg, err = _lookup_account(account, "transactions")
    if err:
        return err

    if not os.path.isdir(cfg["csv_dir"]):
        return _not_found(
            f"Expected export directory {cfg['csv_dir']!r} does not exist.",
            account, "transactions",
            hint="Check that the exports filesystem is mounted/migrated correctly on this host.",
        )

    access_token, err = _get_access_token_or_404(cfg["label"], account, "transactions")
    if err:
        return err

    try:
        account_id = get_account_id_by_mask(access_token, cfg["mask"])
        added, modified, removed = fetch_all_transactions(access_token)
        this_account = [t for t in added + modified if t["account_id"] == account_id]
        posted = [t for t in this_account if not t["pending"]]
        current_balance = get_current_balance(access_token, account_id) if account == "101" else None

        today = datetime.date.today().strftime("%Y%m%d")
        output_path = f"{cfg['csv_dir']}/{cfg['csv_prefix']}_{today}.csv"
        cfg["write_csv"](posted, current_balance, output_path)

        # Plaid's own pending->posted transition can lag what the bank's website
        # already shows as cleared by a day or more (Plaid replaces the pending
        # transaction with a new posted one rather than flipping it in place).
        # Nothing here is lost -- since fetch_all_transactions() always re-pulls
        # the full current snapshot, these show up automatically once Plaid
        # catches up -- but they're worth surfacing so it's not a silent gap.
        excluded_pending = [t for t in this_account if t["pending"]]
        pending_excluded = [
            {
                "date": t["date"].isoformat() if hasattr(t["date"], "isoformat") else t["date"],
                "description": t.get("name") or "",
                # Plaid convention: positive amount = money out, negative = money in.
                "amount": f"{t['amount']:.2f}",
            }
            for t in sorted(excluded_pending, key=lambda t: t["date"], reverse=True)
        ]

        body = {
            "status": "ok",
            "rows_written": len(posted),
            "output_path": output_path,
            "pending_excluded_count": len(pending_excluded),
            "pending_excluded": pending_excluded,
        }
        return _respond(200, body, account, "transactions")

    except plaid.ApiException as e:
        return _plaid_error(e, account, "transactions")
    except Exception as e:
        return _internal_error(e, account, "transactions")


@app.route("/exports/balance/<account>", methods=["POST"])
def export_balance(account):
    cfg, err = _lookup_account(account, "balance")
    if err:
        return err

    if not cfg["supports_balance"]:
        return _not_found(
            f"Balance export is not supported for account {account!r} "
            "(no statement-balance reconciliation is done for this account).",
            account, "balance",
        )

    if not os.path.isdir(BALANCE_OUTPUT_DIR):
        return _not_found(
            f"Expected balance output directory {BALANCE_OUTPUT_DIR!r} does not exist.",
            account, "balance",
            hint="Check that the exports filesystem is mounted/migrated correctly on this host.",
        )

    access_token, err = _get_access_token_or_404(cfg["label"], account, "balance")
    if err:
        return err

    try:
        account_id = get_account_id_by_mask(access_token, cfg["mask"])
        current_balance = get_current_balance(access_token, account_id)
        last_statement_balance = get_last_statement_balance(access_token, account_id)

        output_path = f"{BALANCE_OUTPUT_DIR}/{cfg['balance_filename']}"
        write_balance_snapshot(current_balance, last_statement_balance, output_path)

        body = {
            "status": "ok",
            "currentBalance": f"{current_balance:.2f}",
            "lastStatementBalance": f"{last_statement_balance:.2f}",
            "output_path": output_path,
        }
        return _respond(200, body, account, "balance")

    except plaid.ApiException as e:
        return _plaid_error(e, account, "balance")
    except Exception as e:
        return _internal_error(e, account, "balance")


@app.route("/health", methods=["GET"])
def health():
    """No Plaid calls -- pure local checks, so this works even if Plaid itself
    is down, and is the first thing to hit after a server migration."""
    report = {}
    for key, cfg in ACCOUNTS.items():
        _, token_err = _get_access_token_or_404(cfg["label"], key, "health")
        report[key] = {
            "csv_dir_exists": os.path.isdir(cfg["csv_dir"]),
            "token_present": token_err is None,
            "supports_balance": cfg["supports_balance"],
        }
    report["balance_output_dir_exists"] = os.path.isdir(BALANCE_OUTPUT_DIR)
    return jsonify(report), 200


if __name__ == "__main__":
    print("\nExport trigger API on http://0.0.0.0:8090")
    print("Example: curl -X POST http://<dell1-LAN-IP>:8090/exports/transactions/301")
    print("Example: curl -X POST http://<dell1-LAN-IP>:8090/exports/balance/301")
    print("Example: curl http://<dell1-LAN-IP>:8090/health\n")
    app.run(host="0.0.0.0", port=8090)
