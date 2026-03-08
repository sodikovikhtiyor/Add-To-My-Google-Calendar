import json
import logging
import os

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
