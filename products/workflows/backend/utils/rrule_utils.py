from datetime import datetime

import pytz
from dateutil.rrule import rrulestr


def validate_rrule(rrule_string: str) -> None:
    """Validate an RRULE string. Raises ValueError if invalid."""
    rrulestr(rrule_string)


def compute_next_occurrences(
    rrule_string: str,
    starts_at: datetime,
    timezone_str: str = "UTC",
    after: datetime | None = None,
    count: int = 1,
) -> list[datetime]:
    """
    Compute the next `count` occurrences from an RRULE string.

    Expands the RRULE in the given timezone so that "9 AM Europe/Prague"
    stays at 9 AM local time across DST changes, then converts results to UTC.

    Uses naive datetimes for RRULE expansion (dateutil doesn't handle DST
    with timezone-aware dtstart), then localizes each result to get the
    correct UTC offset for that date.
    """
    tz = pytz.timezone(timezone_str)

    # Convert starts_at to naive local time for RRULE expansion
    if starts_at.tzinfo is not None:
        starts_at_naive = starts_at.astimezone(tz).replace(tzinfo=None)
    else:
        starts_at_naive = starts_at

    rule = rrulestr(rrule_string, dtstart=starts_at_naive, ignoretz=True)

    if after is None:
        after_naive = datetime.now(tz).replace(tzinfo=None)
    elif after.tzinfo is not None:
        after_naive = after.astimezone(tz).replace(tzinfo=None)
    else:
        after_naive = pytz.utc.localize(after).astimezone(tz).replace(tzinfo=None)

    occurrences: list[datetime] = []
    current = after_naive
    for _ in range(count * 10):  # Safety limit
        next_dt = rule.after(current, inc=False)
        if next_dt is None:
            break
        # Localize the naive result in the target timezone (applies correct DST offset)
        # then convert to UTC for storage
        localized = tz.localize(next_dt)
        occurrences.append(localized.astimezone(pytz.utc))
        if len(occurrences) >= count:
            break
        current = next_dt

    return occurrences
