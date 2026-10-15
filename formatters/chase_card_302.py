"""Formatter for Chase credit card #302 (kids' shared card, mask 4803) -> bookkeeping-software CSV.

Target format (from a real Chase export, Chase4803_Activity_*.csv) -- confirmed
identical to card 301's format:
    Header: Transaction Date,Post Date,Description,Category,Type,Amount,Memo
    No trailing comma quirk (7 fields per row, matching the 7-column header).
    Description is never quoted, regardless of content.
    Amount sign convention: Sale/Fee negative, Payment/Return positive.
    Rows are sorted by Post Date descending (most recent first).
    No Balance column -- Chase/Citi credit cards don't expose a running
    balance the way checking does.

Fields actually consumed by the bookkeeping software: Transaction Date,
Description, Amount (it posts using the purchase date, not the post date).
Post Date, Category, and Type have no attempted Plaid mapping -- Category
uses a different taxonomy in Plaid, and Type/Post Date are left blank/best-
effort since they aren't consumed -- the columns must still exist so the CSV
shape (and pandas dataframe import) doesn't change.
"""

HEADER = ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"]


def format_chase_card_302_rows(transactions):
    """Return CSV lines (header + data), newest-first by Post Date."""
    ordered = sorted(enumerate(transactions), key=lambda pair: pair[1]["date"], reverse=True)

    lines = [",".join(HEADER)]
    for _, txn in ordered:
        # Same accepted limitation as card 301: authorized_date (used for
        # Transaction Date) disagrees with Chase's real Transaction Date on a
        # minority of transactions, always by exactly 1 day. Fall back to
        # date if ever missing.
        transaction_date = (txn.get("authorized_date") or txn["date"]).strftime("%m/%d/%Y")
        post_date = txn["date"].strftime("%m/%d/%Y")
        description = txn.get("name") or ""
        category = ""
        type_ = ""
        amount = f"{-txn['amount']:.2f}"
        memo = ""

        row = [transaction_date, post_date, description, category, type_, amount, memo]
        lines.append(",".join(row))

    return lines


def write_chase_card_302_csv(transactions, output_path):
    lines = format_chase_card_302_rows(transactions)
    with open(output_path, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
