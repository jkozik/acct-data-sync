"""
Formatter for Chase checking account #1018 -> bookkeeping-software CSV.

Target format (from a real Chase export, Chase1018_Activity_*.csv):
    Header:  Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
    Each data row has an extra trailing comma (8 comma-separated fields for
    7 header names) -- reproduced here since the bookkeeping software expects it.
    Only Description is quoted, regardless of content.
    Amount sign convention: negative = money out, positive = money in.
    Rows are sorted by Posting Date descending (most recent first).

Fields actually consumed by the bookkeeping software: Posting Date,
Description, Amount, Balance, Check or Slip #. Details and Type have no
reliable Plaid equivalent and are left blank -- the columns must still exist
so the CSV shape (and pandas dataframe import) doesn't change.
"""

HEADER = ["Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"]


def _csv_quote(value):
    return '"' + str(value).replace('"', '""') + '"'


def _compute_running_balances(transactions, current_balance):
    """Reconstruct a running Balance per transaction_id.

    Plaid does not return a per-transaction balance (running_balance is null
    in Sandbox). Instead, anchor to the account's real current balance (from
    /accounts/balance/get, via balances.get_current_balance) and walk
    backward from the most recent transaction to the oldest, undoing each
    transaction's effect in turn. `transactions` is assumed to already be
    posted-only (no pending) so this lines up with current_balance and with
    the bookkeeping workflow, which only deals with posted transactions.
    """
    newest_first = sorted(enumerate(transactions), key=lambda pair: pair[1]["date"], reverse=True)

    balances = {}
    running = current_balance
    for _, txn in newest_first:
        balances[txn["transaction_id"]] = running
        running += txn["amount"]  # Plaid: +out/-in, so this undoes the txn's effect
    return balances


def format_chase_checking_rows(transactions, current_balance):
    """Return CSV lines (header + data), newest-first, matching the real export."""
    balances = _compute_running_balances(transactions, current_balance)

    # Stable sort descending by date; Plaid's own order is not date-sorted at
    # all, so this sort is necessary (confirmed empirically), but ties within
    # a single date keep Plaid's original relative order rather than
    # inventing an intraday ordering we have no data for.
    ordered = sorted(enumerate(transactions), key=lambda pair: pair[1]["date"], reverse=True)

    lines = [",".join(HEADER)]
    for _, txn in ordered:
        details = ""
        posting_date = txn["date"].strftime("%m/%d/%Y")
        description = _csv_quote(txn.get("name") or "")
        amount = f"{-txn['amount']:.2f}"
        type_ = ""
        balance = f"{balances[txn['transaction_id']]:.2f}"
        check_or_slip = txn.get("check_number") or ""

        row = [details, posting_date, description, amount, type_, balance, check_or_slip, ""]
        lines.append(",".join(row))

    return lines


def write_chase_checking_csv(transactions, current_balance, output_path):
    lines = format_chase_checking_rows(transactions, current_balance)
    with open(output_path, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
