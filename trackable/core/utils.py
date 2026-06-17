from decimal import Decimal, ROUND_HALF_UP


def hours_and_minutes_to_decimal(hours, minutes):
    """Convert hours and minutes into decimal hours.

    Examples:
        4 hours, 20 minutes -> Decimal("4.3333")
        40 hours, 0 minutes -> Decimal("40.0000")
    """
    if hours is None:
        hours = 0
    if minutes is None:
        minutes = 0
    return (Decimal(hours) + Decimal(minutes) / 60).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def decimal_to_hours_and_minutes(value):
    """Convert decimal hours into (hours, minutes) tuple.

    Examples:
        Decimal("4.3333") -> (4, 20)
        Decimal("40.0000") -> (40, 0)
    """
    if value is None:
        return (0, 0)
    value = Decimal(value)
    hours = int(value)
    minutes = int((value - hours) * 60 + Decimal("0.5"))
    return (hours, minutes)
