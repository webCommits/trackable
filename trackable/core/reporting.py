"""Pure helpers for computing monthly report send days and periods.

Kept free of Django ORM/settings access so they are trivial to unit test.
"""
import calendar
from datetime import date, timedelta

MIN_REPORT_DAY = 1
MAX_REPORT_DAY = 28


def parse_monthly_report_day(raw):
    """Parse the MONTHLY_REPORT_DAY setting/option value.

    Returns ``None`` for an empty value (falls back to calendar-month mode,
    i.e. send on the last day of the month).

    Raises ``ValueError`` if the value is not an integer, or not within
    ``MIN_REPORT_DAY``..``MAX_REPORT_DAY`` (inclusive). Day 29-31 are
    rejected because they don't exist in every month.
    """
    if raw is None:
        return None

    raw = str(raw).strip()
    if raw == "":
        return None

    try:
        day = int(raw)
    except ValueError:
        raise ValueError(
            f"MONTHLY_REPORT_DAY must be an integer between {MIN_REPORT_DAY} "
            f"and {MAX_REPORT_DAY}, got {raw!r}."
        )

    if not (MIN_REPORT_DAY <= day <= MAX_REPORT_DAY):
        raise ValueError(
            f"MONTHLY_REPORT_DAY must be between {MIN_REPORT_DAY} and "
            f"{MAX_REPORT_DAY}, got {day}."
        )

    return day


def report_period(today, day):
    """Return the (start, end) date range for a report triggered `today`.

    Returns ``None`` if `today` is not a send day for the given
    configuration, in which case no email should be sent.

    - ``day`` is ``None``: calendar-month mode. The send day is the last
      day of today's month; the period is the 1st through the last day of
      that month (the pre-existing behavior).
    - ``day`` is an int (1-28): cutoff mode. The send day is the `day`th of
      every month; the period runs from the day after the `day`th of the
      previous month through today (inclusive), so consecutive periods
      never overlap and never leave a gap.
    """
    if day is None:
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day != last_day:
            return None
        start = date(today.year, today.month, 1)
        end = date(today.year, today.month, last_day)
        return (start, end)

    if today.day != day:
        return None

    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    prev_last_day = calendar.monthrange(prev_year, prev_month)[1]
    prev_period_day = min(day, prev_last_day)
    start = date(prev_year, prev_month, prev_period_day) + timedelta(days=1)
    end = today
    return (start, end)


def report_period_label(start, end, day):
    """Human-readable label for the period, for email subject/body/PDF title."""
    if day is None:
        return start.strftime("%B %Y")
    return f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"
