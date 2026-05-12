from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from anthropic import Anthropic

from models.event import Event

logger = logging.getLogger(__name__)

_client: Anthropic | None = None

# Resolve project-level .env so the key is always available,
# even if this module is imported before bot.py's load_dotenv runs.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        # Ensure .env is loaded; override=True because the system env may
        # contain an empty ANTHROPIC_API_KEY that shadows the .env value.
        load_dotenv(_ENV_PATH, override=True)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        logger.info("Initializing Anthropic client (key length: %d)", len(api_key))
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is empty. "
                f"Checked os.environ and {_ENV_PATH}. "
                "Make sure the key is set in your .env file."
            )
        _client = Anthropic(api_key=api_key)
    return _client

_SYSTEM_PROMPT = """\
You extract calendar event details from text. Return ONLY a raw JSON object — no markdown fences, no explanation.

JSON schema:
{{
  "title": "string (required) — concise event name",
  "date": "YYYY-MM-DD (required)",
  "start_time": "HH:MM in 24h format (required)",
  "end_time": "HH:MM in 24h format (optional) — omit if not mentioned, caller will default to +1h",
  "location": "string or null",
  "description": "string or null — any extra details worth noting"
}}

If no clear event with a date/time is present, return exactly: {{"error": "no event"}}

Today's date: {today}
Current time: {now}
"""

_SYSTEM_PROMPT_V2 = """\
You detect calendar actions from text. Return ONLY a raw JSON object — no markdown fences, no explanation.

Return exactly one of these shapes:

SHAPE A — create a new event:
{{
  "intent": "create",
  "title": "string (required) — concise event name",
  "date": "YYYY-MM-DD (required)",
  "start_time": "HH:MM in 24h format (required)",
  "end_time": "HH:MM in 24h format (optional) — omit if not mentioned",
  "location": "string or null",
  "description": "string or null — any extra details worth noting"
}}

SHAPE B — update an existing event (reschedule, rename, move, change):
{{
  "intent": "update",
  "search": {{
    "title_hint": "string — approximate title of the event to find",
    "date": "YYYY-MM-DD or null — current date of the event being updated",
    "start_time": "HH:MM or null — current start time of the event"
  }},
  "changes": {{
    "title": "string or null — new title (null if unchanged)",
    "date": "YYYY-MM-DD or null — new date (null if unchanged)",
    "start_time": "HH:MM or null — new start time (null if unchanged)",
    "end_time": "HH:MM or null — new end time (null if unchanged)",
    "location": "string or null — new location (null if unchanged)",
    "description": "string or null — new description (null if unchanged)"
  }}
}}

SHAPE C — delete an existing event (remove, cancel, delete):
{{
  "intent": "delete",
  "search": {{
    "title_hint": "string — approximate title of the event to find",
    "date": "YYYY-MM-DD or null — date of the event",
    "start_time": "HH:MM or null — start time of the event"
  }}
}}

If no clear calendar action is present, return exactly: {{"error": "no event"}}

Today's date: {today}
Current time: {now}
"""


def parse_event_from_image(image_bytes: bytes, media_type: str = "image/jpeg", caption: str | None = None) -> Optional[Event]:
    """Send an image to Claude vision and return a structured Event, or None."""
    now = datetime.now()
    system = _SYSTEM_PROMPT.format(
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
    )

    user_text = "Extract calendar event details from this image."
    if caption:
        user_text += f"\n\nAdditional context from the user: {caption}"

    image_b64 = base64.standard_b64encode(image_bytes).decode()
    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": user_text,
                },
            ],
        }],
    )

    raw = response.content[0].text.strip()
    logger.info("AI vision parser raw response: %s", raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {raw[:100]}")
    json_str = raw[start : end + 1]

    data = json.loads(json_str)

    if "error" in data:
        return None

    date_str = data["date"]
    start_dt = datetime.strptime(f"{date_str} {data['start_time']}", "%Y-%m-%d %H:%M")

    if data.get("end_time"):
        end_dt = datetime.strptime(f"{date_str} {data['end_time']}", "%Y-%m-%d %H:%M")
    else:
        end_dt = start_dt + timedelta(hours=1)

    return Event(
        title=data["title"],
        start_dt=start_dt,
        end_dt=end_dt,
        location=data.get("location"),
        description=data.get("description"),
    )


def parse_event(text: str) -> Optional[Event]:
    """
    Send text to Claude and return a structured Event, or None if no event is found.
    Raises on unexpected API or JSON errors.
    """
    now = datetime.now()
    system = _SYSTEM_PROMPT.format(
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
    )

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": text}],
    )

    raw = response.content[0].text.strip()
    logger.info("AI parser raw response: %s", raw)

    # Extract the JSON object from the response — find first { to last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {raw[:100]}")
    json_str = raw[start : end + 1]

    data = json.loads(json_str)

    if "error" in data:
        return None

    date_str = data["date"]
    start_dt = datetime.strptime(f"{date_str} {data['start_time']}", "%Y-%m-%d %H:%M")

    if data.get("end_time"):
        end_dt = datetime.strptime(f"{date_str} {data['end_time']}", "%Y-%m-%d %H:%M")
    else:
        end_dt = start_dt + timedelta(hours=1)

    return Event(
        title=data["title"],
        start_dt=start_dt,
        end_dt=end_dt,
        location=data.get("location"),
        description=data.get("description"),
    )


def parse_intent(text: str) -> dict | None:
    """
    Send text to Claude and return the raw intent dict, or None on API/JSON errors.
    The dict has an "intent" key ("create", "update", "delete") or an "error" key.
    Raises on unexpected errors.
    """
    now = datetime.now()
    system = _SYSTEM_PROMPT_V2.format(
        today=now.strftime("%Y-%m-%d"),
        now=now.strftime("%H:%M"),
    )

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": text}],
    )

    raw = response.content[0].text.strip()
    logger.info("AI intent parser raw response: %s", raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {raw[:100]}")
    json_str = raw[start : end + 1]

    return json.loads(json_str)


def apply_changes(original: dict, changes: dict) -> "Event":
    """
    Merge a changes dict (from parse_intent "update" result) onto a Google Calendar
    API event dict and return a new Event with event_id set.
    """
    title = changes.get("title") or original.get("summary", "")
    location = changes.get("location") if changes.get("location") is not None else original.get("location")
    description = changes.get("description") if changes.get("description") is not None else original.get("description")

    start_str = (original.get("start") or {}).get("dateTime", "")
    end_str = (original.get("end") or {}).get("dateTime", "")
    orig_start = datetime.fromisoformat(start_str).replace(tzinfo=None)
    orig_end = datetime.fromisoformat(end_str).replace(tzinfo=None)
    orig_duration = orig_end - orig_start

    if changes.get("date"):
        new_date = datetime.strptime(changes["date"], "%Y-%m-%d").date()
        orig_start = orig_start.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        orig_end = orig_end.replace(year=new_date.year, month=new_date.month, day=new_date.day)

    if changes.get("start_time"):
        h, m = map(int, changes["start_time"].split(":"))
        orig_start = orig_start.replace(hour=h, minute=m, second=0, microsecond=0)
        if not changes.get("end_time"):
            orig_end = orig_start + orig_duration

    if changes.get("end_time"):
        h, m = map(int, changes["end_time"].split(":"))
        orig_end = orig_end.replace(hour=h, minute=m, second=0, microsecond=0)

    return Event(
        title=title,
        start_dt=orig_start,
        end_dt=orig_end,
        location=location,
        description=description,
        event_id=original.get("id"),
    )
