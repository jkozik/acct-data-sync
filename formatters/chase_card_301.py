"""
Formatter for Chase credit card #301 (Sapphire, mask 1818) -> bookkeeping-software CSV.

Target format (from a real Chase export, Chase1818_Activity_*.csv):
    Header: Transaction Date,Post Date,Description,Category,Type,Amount,Memo
    No trailing comma quirk (7 fields per row, matching the 7-column header).
    Description is never quoted, regardless of content.
    Amount sign convention: Sale/Fee negative, Payment/Return positive.
    Rows are sorted by Post Date descending (most recent first) -- confirmed
    empirically against the real sample (Post Date is strictly non-increasing;
    Transaction Date is not).
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


def format_chase_card_301_rows(transactions):
    """Return CSV lines (header + data), newest-first by Post Date."""
    ordered = sorted(enumerate(transactions), key=lambda pair: pair[1]["date"], reverse=True)

    lines = [",".join(HEADER)]
    for _, txn in ordered:
        # Plaid's authorized_date is the closest available proxy for Chase's own
        # "Transaction Date", but disagrees with it (always by exactly 1 day,
        # authorized_date earlier) on ~20-25% of transactions -- verified against
        # a real sample and no better Plaid field exists (Post Date - 1 day is
        # not a reliable substitute either; the real posting gap varies).
        # Accepted as a known limitation. Fall back to date if ever missing.
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


def write_chase_card_301_csv(transactions, output_path):
    lines = format_chase_card_301_rows(transactions)
    with open(output_path, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
