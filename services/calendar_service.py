from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import database
from models.event import Event

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _load_credentials(telegram_id: int) -> Credentials | None:
    """Load Google OAuth credentials for a specific user from the database."""
    token_json = database.get_google_token(telegram_id)
    if not token_json:
        return None

    info = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(info, SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            logger.info("Refreshing expired Google token for user %d", telegram_id)
            creds.refresh(Request())
            database.save_google_token(telegram_id, creds.to_json())
        except RefreshError:
            logger.warning(
                "Token refresh failed for user %d — deleting stale token",
                telegram_id,
            )
            database.delete_google_token(telegram_id)
            return None

    return creds


def is_authenticated(telegram_id: int) -> bool:
    creds = _load_credentials(telegram_id)
    return creds is not None and creds.valid


def create_event(event: Event, telegram_id: int) -> str:
    """Create an event in the user's primary Google Calendar. Returns the HTML event link."""
    creds = _load_credentials(telegram_id)
    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar is not connected. Use /auth to connect.")

    # Use per-user timezone from DB, fall back to env var
    user = database.get_user(telegram_id)
    tz = (user or {}).get("timezone") or os.getenv("TIMEZONE", "Europe/Moscow")

    service = build("calendar", "v3", credentials=creds)

    body: dict = {
        "summary": event.title,
        "start": {"dateTime": event.start_dt.isoformat(), "timeZone": tz},
        "end": {"dateTime": event.end_dt.isoformat(), "timeZone": tz},
    }
    if event.location:
        body["location"] = event.location
    if event.description:
        body["description"] = event.description

    result = service.events().insert(calendarId="primary", body=body).execute()
    link: str = result.get("htmlLink", "")
    logger.info("Created event for user %d: %s — %s", telegram_id, event.title, link)
    return link


def list_events(telegram_id: int, time_min: str, time_max: str, max_results: int = 10) -> list[dict]:
    """Fetch events from the user's primary calendar in the given time range.
    time_min / time_max must be ISO 8601 strings (e.g. '2026-05-13T00:00:00Z').
    Returns a list of raw Google Calendar API event dicts."""
    creds = _load_credentials(telegram_id)
    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar is not connected. Use /auth to connect.")
    service = build("calendar", "v3", credentials=creds)
    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def get_event(telegram_id: int, event_id: str) -> dict:
    """Fetch a single event by ID from the user's primary calendar."""
    creds = _load_credentials(telegram_id)
    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar is not connected. Use /auth to connect.")
    service = build("calendar", "v3", credentials=creds)
    return service.events().get(calendarId="primary", eventId=event_id).execute()


def update_event(event_id: str, event: Event, telegram_id: int) -> str:
    """Update an existing event in the user's primary calendar. Returns the HTML event link."""
    creds = _load_credentials(telegram_id)
    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar is not connected. Use /auth to connect.")

    user = database.get_user(telegram_id)
    tz = (user or {}).get("timezone") or os.getenv("TIMEZONE", "Europe/Moscow")

    service = build("calendar", "v3", credentials=creds)
    body: dict = {
        "summary": event.title,
        "start": {"dateTime": event.start_dt.isoformat(), "timeZone": tz},
        "end": {"dateTime": event.end_dt.isoformat(), "timeZone": tz},
    }
    if event.location:
        body["location"] = event.location
    if event.description:
        body["description"] = event.description

    result = service.events().update(calendarId="primary", eventId=event_id, body=body).execute()
    link: str = result.get("htmlLink", "")
    logger.info("Updated event %s for user %d: %s — %s", event_id, telegram_id, event.title, link)
    return link


def delete_event(event_id: str, telegram_id: int) -> None:
    """Permanently delete an event from the user's primary calendar."""
    creds = _load_credentials(telegram_id)
    if not creds or not creds.valid:
        raise RuntimeError("Google Calendar is not connected. Use /auth to connect.")
    service = build("calendar", "v3", credentials=creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    logger.info("Deleted event %s for user %d", event_id, telegram_id)


def find_matching_events(
    telegram_id: int,
    title_hint: str,
    date_str: str | None,
    start_time_str: str | None = None,
) -> list[dict]:
    """Search the user's calendar for events matching a title hint and optional date.
    Returns up to 10 matches ordered by start time."""
    now = datetime.utcnow()

    if date_str:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        time_min = (target - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        time_max = (target + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    events = list_events(telegram_id, time_min, time_max, max_results=20)

    if not title_hint:
        return events[:10]

    hint_lower = title_hint.lower()
    matches = [e for e in events if hint_lower in (e.get("summary") or "").lower()]
    return matches[:10]
