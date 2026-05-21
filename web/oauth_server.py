"""
Lightweight aiohttp server that handles the Google OAuth callback.

Route:  GET /oauth/callback?code=...&state=...

Flow:
  1. User clicks the OAuth URL sent by the bot.
  2. Google redirects here with an authorization code + state.
  3. We look up the state -> telegram_id, exchange code for tokens,
     save tokens to DB, and notify the user in Telegram.
"""
from __future__ import annotations

import json
import logging
import os

import httpx
from aiohttp import web
from google_auth_oauthlib.flow import Flow

import database
from locales import get_text

logger = logging.getLogger(__name__)

_runner: web.AppRunner | None = None
_bot_token: str = ""


# ── HTML templates ───────────────────────────────────────

_PRIVACY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy &amp; Data Use — ATMGC</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #222; }
    h1 { font-size: 1.6em; } h2 { font-size: 1.15em; margin-top: 2em; }
    a { color: #1a73e8; }
  </style>
</head>
<body>
  <h1>Privacy Policy &amp; Data Use Statement</h1>
  <p><strong>Application:</strong> ATMGC — Add To My Google Calendar<br>
     <strong>Project ID:</strong> calendar-bot-488812<br>
     <strong>Last updated:</strong> May 21, 2026</p>

  <h2>Google API Limited Use Disclosure</h2>
  <p>
    The use and transfer of information received from Google APIs to ATMGC will adhere to the
    <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>,
    including the <strong>Limited Use requirements</strong>.
  </p>
  <p>Specifically, ATMGC:</p>
  <ul>
    <li>Uses Google Calendar data <strong>only</strong> to create calendar events explicitly requested by the user.</li>
    <li>Does <strong>not</strong> share, sell, or transfer Google user data to any third party for advertising or other purposes unrelated to the app's core functionality.</li>
    <li>Does <strong>not</strong> use Google user data to train, improve, or develop any AI or machine-learning models — including third-party AI models.</li>
    <li>Does <strong>not</strong> allow humans to read Google user data unless the user explicitly requests support assistance, doing so is necessary for security purposes, or required by law.</li>
  </ul>

  <h2>Data We Access</h2>
  <p>ATMGC requests the following Google OAuth scope:</p>
  <ul>
    <li><code>https://www.googleapis.com/auth/calendar</code> — used solely to create Google Calendar events on the authenticated user's behalf.</li>
  </ul>
  <p>No other Google account data is accessed, read, or stored.</p>

  <h2>Third-Party AI Services</h2>
  <p>ATMGC uses third-party AI services to process user-provided message text and voice recordings <em>before</em> creating a calendar event. These services receive only the content of messages the user directly sends to the bot:</p>
  <ul>
    <li><strong>Anthropic Claude</strong> (claude-sonnet-4-6) — parses natural language text to extract event details (title, date, time, location). No Google API data is passed to this service.</li>
    <li><strong>Google Gemini</strong> (gemini-2.5-flash) — transcribes voice messages to text. Audio is uploaded temporarily via the Gemini Files API and is not retained. No Google Calendar data is passed to this service.</li>
  </ul>
  <p>
    <strong>No data received from Google Workspace APIs is sent to, stored by, or used to train any AI model.</strong>
    The AI services receive only the raw message text or audio provided directly by the user — not any data retrieved from Google Calendar or other Google services.
  </p>

  <h2>Data Retention</h2>
  <ul>
    <li>Google OAuth tokens are stored in an encrypted SQLite database on the server and used only to authenticate Calendar API calls on the user's behalf.</li>
    <li>No calendar event data is retained after the event is created.</li>
    <li>Users may revoke access at any time via their <a href="https://myaccount.google.com/permissions">Google Account permissions page</a>.</li>
  </ul>

  <h2>Contact</h2>
  <p>For questions about data use or to request data deletion, contact: <a href="mailto:ihtiyor2655742@gmail.com">ihtiyor2655742@gmail.com</a></p>
</body>
</html>
"""


async def _handle_privacy(_request: web.Request) -> web.Response:
    return web.Response(text=_PRIVACY_HTML, content_type="text/html")


def _success_html(lang: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{get_text("oauth_success_title", lang)}</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
  <h1>&#10004; {get_text("oauth_success_title", lang)}</h1>
  <p>{get_text("oauth_success_msg", lang)}</p>
  <p>{get_text("oauth_success_close", lang)}</p>
</body>
</html>
"""


def _error_html(message: str, lang: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{get_text("oauth_error_title", lang)}</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
  <h1>&#10008; {get_text("oauth_error_title", lang)}</h1>
  <p>{message}</p>
  <p>{get_text("oauth_error_retry", lang)}</p>
</body>
</html>
"""


# ── Callback handler ────────────────────────────────────

async def _handle_callback(request: web.Request) -> web.Response:
    code = request.query.get("code")
    state = request.query.get("state")
    error = request.query.get("error")

    # Default language until we know the user
    lang = "en"

    if error:
        logger.warning("OAuth error from Google: %s", error)
        return web.Response(
            text=_error_html(f"Google returned an error: {error}", lang),
            content_type="text/html",
        )

    if not code or not state:
        return web.Response(
            text=_error_html("Missing code or state parameter.", lang),
            content_type="text/html",
        )

    # Look up state -> telegram_id + code_verifier
    state_data = database.pop_oauth_state(state)
    if state_data is None:
        return web.Response(
            text=_error_html(
                "Invalid or expired authorization. Please try /auth again.", lang
            ),
            content_type="text/html",
        )

    telegram_id = state_data["telegram_id"]
    code_verifier = state_data["code_verifier"]

    # Now we know the user — get their language
    user = database.get_user(telegram_id)
    if user and user.get("language"):
        lang = user["language"]

    # Exchange authorization code for tokens
    try:
        secrets_path = os.getenv(
            "GOOGLE_CLIENT_SECRETS_PATH", "credentials/client_secrets_web.json"
        )
        redirect_uri = os.getenv(
            "OAUTH_REDIRECT_URI", "https://calbot.nawys.uz/oauth/callback"
        )

        with open(secrets_path) as f:
            client_config = json.load(f)

        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/calendar"],
            redirect_uri=redirect_uri,
        )
        # Restore PKCE code_verifier from the original authorization request
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as e:
        logger.error("Token exchange failed for user %d: %s", telegram_id, e)
        return web.Response(
            text=_error_html(f"Token exchange failed: {e}", lang),
            content_type="text/html",
        )

    # Save token to database
    database.save_google_token(telegram_id, creds.to_json())

    # Notify user via Telegram Bot API
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{_bot_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": get_text("oauth_connected", lang),
                },
            )
    except Exception as e:
        logger.error("Failed to send Telegram confirmation to %d: %s", telegram_id, e)

    logger.info("OAuth completed for user %d", telegram_id)
    return web.Response(text=_success_html(lang), content_type="text/html")


# ── Lifecycle ───────────────────────────────────────────

async def start_oauth_server(bot_token: str) -> None:
    global _runner, _bot_token
    _bot_token = bot_token

    app = web.Application()
    app.router.add_get("/oauth/callback", _handle_callback)
    app.router.add_get("/privacy", _handle_privacy)

    port = int(os.getenv("OAUTH_SERVER_PORT", "8080"))
    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, "0.0.0.0", port)
    await site.start()
    logger.info("OAuth callback server started on port %d", port)


async def stop_oauth_server() -> None:
    global _runner
    if _runner:
        await _runner.cleanup()
        _runner = None
        logger.info("OAuth callback server stopped")
