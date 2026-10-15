"""
Pull transactions for a stored access_token via /transactions/sync and print as JSON.

Usage:
    .venv/bin/python sync_transactions.py <label>

Example:
    .venv/bin/python sync_transactions.py Chase101Checking
"""
import sys
import json

import plaid
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from plaid_client import client, raise_friendly_if_login_required
from tokens import get_access_token


def fetch_all_transactions(access_token):
    """Page through /transactions/sync until has_more is False.

    Returns (added, modified, removed) lists of transactions (as dicts).
    """
    added, modified, removed = [], [], []
    cursor = None

    while True:
        request_kwargs = {"access_token": access_token}
        if cursor:
            request_kwargs["cursor"] = cursor
        req = TransactionsSyncRequest(**request_kwargs)

        try:
            resp = client.transactions_sync(req)
        except plaid.ApiException as e:
            raise_friendly_if_login_required(e)

        added.extend(t.to_dict() for t in resp.added)
        modified.extend(t.to_dict() for t in resp.modified)
        removed.extend(r.to_dict() for r in resp.removed)

        cursor = resp.next_cursor
        if not resp.has_more:
            break

    return added, modified, removed


def main():
    if len(sys.argv) != 2:
        print("Usage: python sync_transactions.py <label>", file=sys.stderr)
        sys.exit(1)

    label = sys.argv[1]
    access_token = get_access_token(label)

    added, modified, removed = fetch_all_transactions(access_token)

    print(json.dumps({
        "added": added,
        "modified": modified,
        "removed": removed,
    }, indent=2, default=str))

    print(
        f"\n--- summary: {len(added)} added, {len(modified)} modified, "
        f"{len(removed)} removed ---",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
