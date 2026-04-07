"""Parse natural language reminder requests into (text, datetime) pairs."""
import re
import logging
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Berlin")

# Patterns that indicate a reminder intent
REMINDER_TRIGGERS = [
    r"remind me\s+(?:to\s+)?(.+)",
    r"reminder[:\s]+(.+)",
    r"תזכיר לי\s+(.+)",
    r"erinnere mich\s+(?:an\s+|daran\s+)?(.+)",
    r"set (?:a )?reminder\s+(?:to\s+)?(.+)",
]

# Time extraction patterns — order matters (most specific first)
TIME_PATTERNS = [
    # "in X hours/minutes"
    (r"\bin\s+(\d+)\s*(hours?|h)\b", "delta_hours"),
    (r"\bin\s+(\d+)\s*(minutes?|mins?|m)\b", "delta_minutes"),
    # "at HH:MM" or "at Hpm/am"
    (r"\bat\s+(\d{1,2}):(\d{2})\b", "at_hhmm"),
    (r"\bat\s+(\d{1,2})\s*(am|pm)\b", "at_hap"),
    # Hebrew time "ב-HH:MM"
    (r"ב-?(\d{1,2}):(\d{2})\b", "at_hhmm"),
    # "on April 15" / "on 15 April" / "on 15.04"
    (r"\bon\s+(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", "on_month_day"),
    (r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\b", "on_day_month"),
    (r"\bon\s+(\d{1,2})\.(\d{1,2})\b", "on_dd_mm"),
    # "tomorrow"
    (r"\btomorrow\b", "tomorrow"),
    (r"\bמחר\b", "tomorrow"),
    (r"\bmorgen\b", "tomorrow"),
    # "tonight"
    (r"\btonight\b", "tonight"),
]

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _clean_reminder_text(text: str) -> str:
    """Remove time-related fragments from the reminder text."""
    cleaned = text
    remove_patterns = [
        r"\bin\s+\d+\s*(hours?|h|minutes?|mins?|m)\b",
        r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b",
        r"ב-?\d{1,2}(:\d{2})?\b",
        r"\bon\s+\w+\s+\d{1,2}(st|nd|rd|th)?\b",
        r"\bon\s+\d{1,2}(st|nd|rd|th)?\s+\w+\b",
        r"\bon\s+\d{1,2}\.\d{1,2}\b",
        r"\btomorrow\b", r"\bמחר\b", r"\bmorgen\b",
        r"\btonight\b",
    ]
    for pat in remove_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    # Collapse whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().rstrip(".,;")
    return cleaned


def parse_reminder(message: str) -> tuple[str, datetime] | None:
    """
    Parse a natural language reminder message.

    Returns (reminder_text, remind_at_datetime) or None if not a reminder.
    All datetimes are in Europe/Berlin timezone.
    """
    message_lower = message.lower()

    # Check if this is a reminder request
    body = None
    for pattern in REMINDER_TRIGGERS:
        m = re.search(pattern, message_lower)
        if m:
            # Use the original message casing for the captured body
            start = m.start(1)
            body = message[start : start + len(m.group(1))]
            break

    if body is None:
        return None

    now = datetime.now(TZ)
    remind_at = None
    matched_time_type = None

    for pattern, time_type in TIME_PATTERNS:
        m = re.search(pattern, body, re.IGNORECASE)
        if not m:
            m = re.search(pattern, message_lower, re.IGNORECASE)
        if not m:
            continue

        matched_time_type = time_type

        if time_type == "delta_hours":
            remind_at = now + timedelta(hours=int(m.group(1)))
        elif time_type == "delta_minutes":
            remind_at = now + timedelta(minutes=int(m.group(1)))
        elif time_type == "at_hhmm":
            hour, minute = int(m.group(1)), int(m.group(2))
            remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if remind_at <= now:
                remind_at += timedelta(days=1)
        elif time_type == "at_hap":
            hour = int(m.group(1))
            if m.group(2).lower() == "pm" and hour != 12:
                hour += 12
            elif m.group(2).lower() == "am" and hour == 12:
                hour = 0
            remind_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if remind_at <= now:
                remind_at += timedelta(days=1)
        elif time_type == "on_month_day":
            month_name = m.group(1).lower()
            day = int(m.group(2))
            month = MONTHS.get(month_name)
            if month:
                year = now.year
                candidate = now.replace(month=month, day=day, hour=9, minute=0, second=0, microsecond=0)
                if candidate < now:
                    candidate = candidate.replace(year=year + 1)
                remind_at = candidate
        elif time_type == "on_day_month":
            day = int(m.group(1))
            month_name = m.group(2).lower()
            month = MONTHS.get(month_name)
            if month:
                year = now.year
                candidate = now.replace(month=month, day=day, hour=9, minute=0, second=0, microsecond=0)
                if candidate < now:
                    candidate = candidate.replace(year=year + 1)
                remind_at = candidate
        elif time_type == "on_dd_mm":
            day, month = int(m.group(1)), int(m.group(2))
            year = now.year
            candidate = now.replace(month=month, day=day, hour=9, minute=0, second=0, microsecond=0)
            if candidate < now:
                candidate = candidate.replace(year=year + 1)
            remind_at = candidate
        elif time_type == "tomorrow":
            remind_at = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif time_type == "tonight":
            remind_at = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if remind_at <= now:
                remind_at += timedelta(days=1)

        if remind_at:
            break

    if remind_at is None:
        # No time found — default to 1 hour from now
        remind_at = now + timedelta(hours=1)

    # Also check if "tomorrow" was found separately and combine with a specific time
    if matched_time_type in ("at_hhmm", "at_hap"):
        if re.search(r"\btomorrow\b|\bמחר\b|\bmorgen\b", message_lower):
            # Shift to tomorrow if not already
            tomorrow = now + timedelta(days=1)
            remind_at = remind_at.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)

    reminder_text = _clean_reminder_text(body)
    if not reminder_text:
        reminder_text = body.strip()

    return reminder_text, remind_at
