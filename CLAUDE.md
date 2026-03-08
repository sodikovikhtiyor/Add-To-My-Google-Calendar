# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

A Telegram bot that receives forwarded posts/messages, uses Claude AI to extract structured event data, confirms with the user, and creates events in Google Calendar.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# One-time Google OAuth (opens browser, saves credentials/token.json)
python scripts/auth.py

# Run the bot
python bot.py
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `GOOGLE_CLIENT_SECRETS_PATH` — path to OAuth client secrets JSON (default: `credentials/client_secrets.json`)
- `GOOGLE_CREDENTIALS_PATH` — where the OAuth token is saved (default: `credentials/token.json`)
- `TIMEZONE` — IANA timezone string (default: `Europe/Moscow`)

Google OAuth requires: Calendar API enabled + OAuth 2.0 Client ID of type **Desktop app** in Google Cloud Console.

## Architecture

### Core Flow

```
User message → handle_message → parse_event (Claude) → inline keyboard preview
                                                              ↓ confirm
                                                      create_event (Google Calendar)
                                                              ↓
                                                        event HTML link
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `bot.py` | Entry point; wires handlers to `Application` and starts polling |
| `handlers/message_handler.py` | Receives text/forwarded messages; calls `parse_event`; stores pending `Event` in `context.user_data`; sends inline keyboard preview; `handle_confirmation` processes button callbacks |
| `handlers/command_handler.py` | `/start`, `/help`, `/auth` (checks auth status only) |
| `services/ai_parser.py` | Sends text to Claude with a structured JSON extraction prompt; strips markdown fences from response; returns `Event` or `None` |
| `services/calendar_service.py` | Loads/refreshes Google OAuth token; `create_event()` calls Calendar API v3 |
| `models/event.py` | `Event` dataclass: `title`, `start_dt`, `end_dt`, `location`, `description` |
| `scripts/auth.py` | One-time interactive OAuth flow via local server on port 8080; run before starting the bot |

### Pending Event State

After parsing, the `Event` is stored in `context.user_data["pending_event"]` (per-user, in-memory). The inline keyboard callback (`confirm` / `cancel`) retrieves and pops it. If the bot restarts, pending events are lost and the user must resend.

### Async / Sync Boundary

`calendar_service.py` and `ai_parser.py` are synchronous. Handlers call them via `asyncio.to_thread()` to avoid blocking the event loop.

### Auth Flow

`scripts/auth.py` runs `InstalledAppFlow.run_local_server(port=8080)` — opens a browser, handles the OAuth redirect on localhost, and writes `credentials/token.json`. The bot's `/auth` command only checks whether the token exists and is valid; it does not trigger the OAuth flow.
