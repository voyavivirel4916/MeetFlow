"""RFC3339 at the wire boundary; UTC integer milliseconds in storage."""
from datetime import datetime, timedelta, timezone
import re

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def parse_rfc3339(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value):
        raise ValueError('Use a timezone-qualified RFC3339 datetime.')
    try:
        parsed = datetime.fromisoformat(value.upper().replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('Use a valid RFC3339 datetime.') from None
    return parsed.replace(microsecond=parsed.microsecond // 1000 * 1000)


def to_ms(value: datetime) -> int:
    delta = value - EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def format_ms(value: int) -> str:
    return (EPOCH + timedelta(milliseconds=value)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
