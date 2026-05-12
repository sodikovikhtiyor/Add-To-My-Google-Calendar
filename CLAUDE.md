# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

A multi-user Telegram bot that receives forwarded posts, voice messages, or typed text, uses Claude AI to extract structured event data, confirms with the user, and creates events in their Google Calendar.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (starts both Telegram polling and the OAuth callback server)
python bot.py
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `ANTHROPIC_API_KEY` — Claude API key for event parsing
- `GEMINI_API_KEY` — Google Gemini API key for voice transcription
- `GOOGLE_CLIENT_SECRETS_PATH` — path to OAuth **Web application** client secrets JSON (default: `credentials/client_secrets_web.json`)
- `OAUTH_REDIRECT_URI` — public HTTPS URL for the OAuth callback (default: `https://calbot.nawys.uz/oauth/callback`)
- `OAUTH_SERVER_PORT` — port for the local OAuth callback server (default: `8080`)
- `DATABASE_PATH` — SQLite database path (default: `data/bot.db`)
- `TIMEZONE` — IANA timezone fallback (default: `Europe/Moscow`; per-user timezone stored in DB)

Google Cloud Console requirements: Calendar API enabled + OAuth 2.0 Client ID of type **Web application** (not Desktop app). Add the `OAUTH_REDIRECT_URI` as an authorized redirect URI.

## Architecture

### Core Flow

```
User message → handle_message ──────────────────────────────────────────────────────────────────┐
User voice   → handle_voice → transcribe_audio (Gemini) ─────────────────────────────────────┐ │
                                                                                               ↓ ↓
                                                              _process_event_text → parse_event (Claude)
                                                                    ↓
                                                        inline keyboard preview (pending_event stored)
                                                                    ↓ confirm
                                                            create_event (Google Calendar API)
                                                                    ↓
                                                              event HTML link
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `bot.py` | Entry point; wires all handlers; starts/stops OAuth server via lifecycle hooks; runs periodic `cleanup_states` job |
| `database.py` | SQLite access layer (WAL mode); tables: `users`, `google_tokens`, `oauth_states`; every function opens/closes its own connection for `asyncio.to_thread` safety |
| `handlers/message_handler.py` | Text/caption handler with registration intercepts; `handle_voice` for voice messages; `handle_contact` for phone sharing; `handle_confirmation` for inline button callbacks |
| `handlers/command_handler.py` | `/start` (registration + language picker), `/help`, `/auth` (generates PKCE OAuth URL), `/lang`; callback handlers for `start_lang:` and `lang:` patterns |
| `services/ai_parser.py` | Calls Claude (`claude-sonnet-4-6`) with a structured JSON extraction prompt; returns `Event` or `None` |
| `services/calendar_service.py` | Loads per-user Google OAuth credentials from DB, auto-refreshes expired tokens, calls Calendar API v3 |
| `services/transcription_service.py` | Uploads OGG audio to Gemini Files API (`gemini-2.5-flash`) and returns transcribed text |
| `web/oauth_server.py` | aiohttp server on `OAUTH_SERVER_PORT`; handles `GET /oauth/callback`; exchanges code for tokens using PKCE; saves to DB; sends Telegram confirmation |
| `locales/` | i18n strings for `en`, `ru`, `uz`; `detect_language()` maps Telegram `language_code` to supported lang |
| `models/event.py` | `Event` dataclass: `title`, `start_dt`, `end_dt`, `location`, `description` |

### Multi-User OAuth Flow

`/auth` generates a UUID state + PKCE code_verifier, stores them in `oauth_states` (expires in 10 min), and sends the user a Google authorization link. After the user authorizes, Google redirects to `OAUTH_REDIRECT_URI`, the aiohttp server exchanges the code for tokens (with PKCE), saves them to `google_tokens` keyed by `telegram_id`, and notifies the user in Telegram. `scripts/auth.py` is a legacy single-user helper — the bot itself handles OAuth end-to-end.

### User Registration Flow

New users: `/start` → language picker (inline keyboard, `start_lang:` prefix) → name (awaiting_name) → phone request (awaiting_phone, optional). State tracked in `context.user_data`. Users are stored in `users` table before any calendar interaction is allowed.

### Pending Event State

After parsing, the `Event` is stored in `context.user_data["pending_event"]`. Inline keyboard callbacks (`confirm` / `cancel`) pop it. Lost on bot restart — user must resend.

### Async / Sync Boundary

`database.py`, `calendar_service.py`, `ai_parser.py`, and `transcription_service.py` are all synchronous. Handlers call them via `asyncio.to_thread()`.

### Localization

All user-facing strings go through `get_text(key, lang, **kwargs)`. Add new keys to all three locale files (`en.py`, `ru.py`, `uz.py`). Language is stored per-user in `users.language`; during registration it's temporarily held in `context.user_data["detected_lang"]`.
