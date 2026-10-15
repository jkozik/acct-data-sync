"""
Export Chase credit card 302 (kids' shared card, mask 4803) transactions to a
CSV matching the bookkeeping software's format, plus a balance snapshot JSON.

Usage:
    .venv/bin/python export_chase_card_302.py <label> [output_csv_path]

If output_csv_path is omitted, writes into the same folder/naming convention
as Chase's own exports for this card.

Example:
    .venv/bin/python export_chase_card_302.py chase_household_login
"""
import sys
import datetime

import plaid

from sync_transactions import fetch_all_transactions
from tokens import get_access_token
from accounts import get_account_id_by_mask
from balances import get_current_balance
from liabilities import get_last_statement_balance
from formatters.chase_card_302 import write_chase_card_302_csv
from formatters.balance_snapshot import write_balance_snapshot
from plaid_client import print_friendly_error_and_exit

DEFAULT_OUTPUT_DIR = "/home/nf/websiteexports/Chase302Export"
BALANCE_OUTPUT_DIR = "/home/nf/websiteexports/PlaidBalances"
ACCOUNT_MASK = "4803"  # a single Plaid item/login can bundle multiple accounts


def default_output_path():
    today = datetime.date.today().strftime("%Y%m%d")
    return f"{DEFAULT_OUTPUT_DIR}/Chase4803_Activity_Plaid_{today}.csv"


def default_balance_output_path():
    # No date stamp: overwritten in place each run so a remote fetch script can
    # always read one fixed, known path instead of discovering "the most recent"
    # file. Kept in a separate folder from the activity CSVs -- the bookkeeping
    # software's reconciliation import grabs the most-recently-created file in
    # an *Export folder regardless of extension, so a same-folder JSON file
    # newer than the CSV gets mistaken for it.
    return f"{BALANCE_OUTPUT_DIR}/Chase4803_Balance_Plaid.json"


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python export_chase_card_302.py <label> [output_csv_path]", file=sys.stderr)
        sys.exit(1)

    label = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else default_output_path()
    access_token = get_access_token(label)

    try:
        account_id = get_account_id_by_mask(access_token, ACCOUNT_MASK)

        added, modified, removed = fetch_all_transactions(access_token)
        posted = [t for t in added + modified if not t["pending"] and t["account_id"] == account_id]

        write_chase_card_302_csv(posted, output_path)
        print(f"Wrote {len(posted)} posted transactions to {output_path}", file=sys.stderr)

        current_balance = get_current_balance(access_token, account_id)
        last_statement_balance = get_last_statement_balance(access_token, account_id)
        balance_output_path = default_balance_output_path()
        write_balance_snapshot(current_balance, last_statement_balance, balance_output_path)
    except plaid.ApiException as e:
        print_friendly_error_and_exit(e)
    print(f"Wrote balance snapshot to {balance_output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
