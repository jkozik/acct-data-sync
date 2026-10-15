"""Formatter for Citi AT&T Universal Card #304 (mask 3166) -> bookkeeping-software CSV.

Target format (from a real Citi export, "Year to date (52).CSV"):
    Header: Status,Date,Description,Debit,Credit
    Status is always "Cleared" in the real export -- it only ever contains
    posted transactions, matching our posted-only filtering.
    Description is always quoted, regardless of content.
    Debit/Credit are separate columns rather than one signed Amount column:
    a purchase populates Debit (positive) and leaves Credit blank; a payment
    populates Credit (negative) and leaves Debit blank.
    No sign flip needed, unlike the Chase formatters: Plaid's convention
    (positive = money out, negative = money in) already matches Citi's
    Debit(positive)/Credit(negative) split directly -- confirmed against the
    real sample (e.g. AUTOPAY rows appear as negative Credit values).
    Rows are sorted by Date descending (most recent first).
    Only one Date column in this export (no separate transaction/post date).
"""

HEADER = ["Status", "Date", "Description", "Debit", "Credit"]


def _csv_quote(value):
    return '"' + str(value).replace('"', '""') + '"'


def format_citi_card_304_rows(transactions):
    """Return CSV lines (header + data), newest-first by Date."""
    ordered = sorted(enumerate(transactions), key=lambda pair: pair[1]["date"], reverse=True)

    lines = [",".join(HEADER)]
    for _, txn in ordered:
        status = "Cleared"
        date = txn["date"].strftime("%m/%d/%Y")
        description = _csv_quote(txn.get("name") or "")
        amount = txn["amount"]
        if amount >= 0:
            debit, credit = f"{amount:.2f}", ""
        else:
            debit, credit = "", f"{amount:.2f}"

        row = [status, date, description, debit, credit]
        lines.append(",".join(row))

    return lines


def write_citi_card_304_csv(transactions, output_path):
    lines = format_citi_card_304_rows(transactions)
    with open(output_path, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
