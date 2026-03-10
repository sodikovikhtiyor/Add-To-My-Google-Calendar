# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

A Telegram bot that receives forwarded posts/messages, uses Claude AI to extract structured event data, confirms with the user, and creates events in Google Calendar.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

Google Calendar authentication is done entirely through the bot's `/auth` command — no separate script is needed.

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `GEMINI_API_KEY` — from Google AI Studio (used for voice transcription)
- `GOOGLE_CLIENT_SECRETS_PATH` — path to the OAuth client secrets JSON (default: `credentials/client_secrets_web.json`)
- `OAUTH_REDIRECT_URI` — the public HTTPS URL where Google will redirect after OAuth, e.g. `https://yourdomain.com/oauth/callback`. **Must be registered in Google Cloud Console.**
- `OAUTH_SERVER_PORT` — local port for the aiohttp OAuth callback server (default: `8080`)
- `DATABASE_PATH` — SQLite database file path (default: `data/bot.db`)
- `TIMEZONE` — IANA timezone string (default: `Europe/Moscow`)

### Google Cloud Setup

The bot uses a **web-based OAuth 2.0 flow** for Google Calendar. Each Telegram user authenticates individually through the bot's `/auth` command. This requires:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Google Calendar API**
4. Create an **OAuth 2.0 Client ID** of type **Web application** (not Desktop app)
5. Under "Authorized redirect URIs", add your `OAUTH_REDIRECT_URI` value exactly
6. Download the JSON and save it as `credentials/client_secrets_web.json` (or the path set in `GOOGLE_CLIENT_SECRETS_PATH`)

> **Important**: The OAuth callback server (aiohttp, port `OAUTH_SERVER_PORT`) must be reachable from the public internet at the domain in `OAUTH_REDIRECT_URI`. Use a reverse proxy (nginx, Caddy, etc.) if running behind NAT.

## Architecture

### Core Flow

```
User message → handle_message → parse_event (Claude) → inline keyboard preview
                                                              ↓ confirm
                                                      create_event (Google Calendar)
                                                              ↓
                                                        event HTML link
```

### /auth Flow (Web OAuth per user)

```
User sends /auth → bot generates OAuth URL (state UUID saved to DB)
                 → user clicks link → Google consent screen
                 → Google redirects to OAUTH_REDIRECT_URI?code=...&state=...
                 → aiohttp callback server (web/oauth_server.py)
                 → exchanges code for token, saves token to DB
                 → notifies user in Telegram
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `bot.py` | Entry point; wires handlers to `Application`; starts/stops the OAuth aiohttp server |
| `handlers/message_handler.py` | Receives text/forwarded messages; calls `parse_event`; stores pending `Event` in `context.user_data`; sends inline keyboard preview; `handle_confirmation` processes button callbacks |
| `handlers/command_handler.py` | `/start`, `/help`, `/auth` (generates per-user OAuth URL), `/lang` |
| `services/ai_parser.py` | Sends text to Claude with a structured JSON extraction prompt; strips markdown fences from response; returns `Event` or `None` |
| `services/calendar_service.py` | Loads/refreshes Google OAuth token from DB; `create_event()` calls Calendar API v3 |
| `services/transcription_service.py` | Transcribes voice messages using Gemini |
| `models/event.py` | `Event` dataclass: `title`, `start_dt`, `end_dt`, `location`, `description` |
| `web/oauth_server.py` | aiohttp server; handles `GET /oauth/callback`; exchanges auth code for token; saves to DB; notifies user via Telegram API |
| `database.py` | SQLite access layer: users, google_tokens, oauth_states tables |

### Pending Event State

After parsing, the `Event` is stored in `context.user_data["pending_event"]` (per-user, in-memory). The inline keyboard callback (`confirm` / `cancel`) retrieves and pops it. If the bot restarts, pending events are lost and the user must resend.

### Async / Sync Boundary

`calendar_service.py` and `ai_parser.py` are synchronous. Handlers call them via `asyncio.to_thread()` to avoid blocking the event loop.

### Token Storage

Google OAuth tokens are stored per-user in the `google_tokens` SQLite table (not in flat files). `calendar_service._load_credentials()` reads from the DB and refreshes expired tokens automatically.
