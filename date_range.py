"""Compute the transaction pull date range."""
import datetime


def get_pull_date_range(today=None):
    """Return (start_date, end_date) as datetime.date objects.

    Default range is year-to-date: Jan 1 of the current year through today.

    Exception: if today falls in January or February, bookkeeping for the
    prior year may still be wrapping up, so the start date instead goes back
    to Jan 1 of the PREVIOUS year (covering ~14 months) rather than starting
    the range on Jan 1 of the current (barely-started) year.
    """
    today = today or datetime.date.today()

    if today.month in (1, 2):
        start_year = today.year - 1
    else:
        start_year = today.year

    start_date = datetime.date(start_year, 1, 1)
    end_date = today
    return start_date, end_date


if __name__ == "__main__":
    # Quick manual check: today, plus one date in Jan and one in Feb, to
    # confirm the exception fires correctly.
    for label, d in [
        ("today", datetime.date.today()),
        ("Jan 15 same year", datetime.date(datetime.date.today().year, 1, 15)),
        ("Feb 28 same year", datetime.date(datetime.date.today().year, 2, 28)),
    ]:
        start, end = get_pull_date_range(d)
        print(f"{label:20s} -> today={d}  From={start}  To={end}")
