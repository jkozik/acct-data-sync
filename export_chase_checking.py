"""
Export Chase checking transactions to a CSV matching the bookkeeping software's format.

Usage:
    .venv/bin/python export_chase_checking.py <label> [output_csv_path]

If output_csv_path is omitted, writes into the same folder/naming convention
as Chase's own exports (the bookkeeping software just picks the newest file
in that folder), e.g. Chase1018_Activity_Plaid_20260831.csv.

Example:
    .venv/bin/python export_chase_checking.py chase_checking_real
"""
import sys
import datetime

import plaid

from sync_transactions import fetch_all_transactions
from tokens import get_access_token
from balances import get_current_balance
from accounts import get_account_id_by_mask
from formatters.chase_checking import write_chase_checking_csv
from plaid_client import print_friendly_error_and_exit

DEFAULT_OUTPUT_DIR = "/home/nf/websiteexports/Chase101Export"
ACCOUNT_MASK = "1018"  # a single Plaid item/login can bundle multiple accounts


def default_output_path():
    today = datetime.date.today().strftime("%Y%m%d")
    return f"{DEFAULT_OUTPUT_DIR}/Chase1018_Activity_Plaid_{today}.csv"


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python export_chase_checking.py <label> [output_csv_path]", file=sys.stderr)
        sys.exit(1)

    label = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else default_output_path()
    access_token = get_access_token(label)

    try:
        account_id = get_account_id_by_mask(access_token, ACCOUNT_MASK)

        added, modified, removed = fetch_all_transactions(access_token)
        # Bookkeeping only deals with posted transactions, and only from this account
        # (a Plaid item/login can bundle other accounts too, e.g. a joint login).
        posted = [t for t in added + modified if not t["pending"] and t["account_id"] == account_id]

        current_balance = get_current_balance(access_token, account_id)

        write_chase_checking_csv(posted, current_balance, output_path)
    except plaid.ApiException as e:
        print_friendly_error_and_exit(e)
    print(f"Wrote {len(posted)} posted transactions to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
