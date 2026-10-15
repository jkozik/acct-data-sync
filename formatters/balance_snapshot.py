"""Writes the {currentBalance, lastStatementBalance} snapshot file used for the
user's Windows-side reconciliation step. Same field names/shape as their existing
Chrome-snippet output (e.g. {currentBalance: '3880.11', lastStatementBalance: '3357.93'}),
just sourced from Plaid instead of scraping the account activity page.
"""
import json


def write_balance_snapshot(current_balance, last_statement_balance, output_path):
    data = {
        "currentBalance": f"{current_balance:.2f}",
        "lastStatementBalance": f"{last_statement_balance:.2f}",
    }
    with open(output_path, "w") as f:
        json.dump(data, f)
