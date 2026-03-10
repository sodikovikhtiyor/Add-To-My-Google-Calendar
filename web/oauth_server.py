"""
Lightweight aiohttp server that handles the Google OAuth callback.

Route:  GET /oauth/callback?code=...&state=...

Flow:
  1. User clicks the OAuth URL sent by the bot.
  2. Google redirects here with an authorization code + state.
  3. We look up the state -> telegram_id, exchange code for tokens,
     save tokens to DB, and notify the user in Telegram.
"""

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
        redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "")

        if not redirect_uri:
            raise ValueError("OAUTH_REDIRECT_URI is not configured on the server.")

        if not os.path.exists(secrets_path):
            raise FileNotFoundError(
                f"Google client secrets file not found: '{secrets_path}'"
            )

        with open(secrets_path) as f:
            client_config = json.load(f)

        if "web" not in client_config and "installed" in client_config:
            raise ValueError(
                "Client secrets are for a Desktop app. "
                "A Web Application OAuth 2.0 client is required."
            )

        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/calendar"],
            redirect_uri=redirect_uri,
        )
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
