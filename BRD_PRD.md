# Business & Product Requirements Document
**Project:** Add-To-My-Google-Calendar (Telegram Calendar Bot)
**Version:** 1.0
**Date:** 2026-03-19
**Status:** Living Document

---

## Part 1 — Business Requirements Document (BRD)

### 1.1 Executive Summary

Users in Telegram-heavy environments (communities, channels, group chats) regularly receive event announcements — conferences, meetups, calls, deadlines — as unstructured text or voice messages. Adding these to Google Calendar is a manual, error-prone process that interrupts workflow. This bot eliminates that friction.

### 1.2 Problem Statement

| Pain Point | Impact |
|---|---|
| Manual copy-paste from Telegram posts to Google Calendar | Wasted time, risk of wrong date/time entry |
| Voice messages contain event info but can't be copied at all | Events missed entirely |
| Non-technical users struggle with Google Calendar's UI | Low adoption of calendar hygiene |
| CIS/Uzbek-speaking users underserved by English-only tools | Accessibility gap |

### 1.3 Business Objectives

1. **Reduce friction** — event creation from a Telegram message in under 10 seconds
2. **Accessibility** — support Russian and Uzbek users natively, not as an afterthought
3. **Zero-config UX** — user never leaves Telegram; no app to install; one-time Google auth setup
4. **Multi-user** — one bot instance serves many independent users, each with isolated calendar access

### 1.4 Stakeholders

| Role | Responsibility |
|---|---|
| Bot owner / developer | Infrastructure, API keys, deployment |
| End users | Telegram users who receive event messages |
| Google Calendar | Stores the resulting events |
| Anthropic (Claude) | AI extraction of event details |
| Google (Gemini) | Voice message transcription |

### 1.5 Scope

**In scope:**
- Telegram bot interface (text, forwarded messages, voice, captions)
- AI-powered event extraction (Claude)
- Voice transcription (Gemini)
- Google Calendar event creation via OAuth
- Multi-language UI: English, Russian, Uzbek
- Multi-user support with per-user OAuth tokens

**Out of scope (v1):**
- Recurring event creation
- Editing events after creation
- Other calendar providers (Outlook, Apple Calendar)
- Web interface
- Payments / premium tier

### 1.6 Constraints

- Google OAuth requires a web redirect URI — a publicly accessible server is needed
- Users must grant Google Calendar write permissions (OAuth scope)
- Anthropic API and Gemini API are paid; costs scale with usage
- Voice messages supported in OGG/Opus format (Telegram default)

### 1.7 Success Metrics

| Metric | Target |
|---|---|
| Event created from text message | < 10 seconds end-to-end |
| Event created from voice message | < 20 seconds end-to-end |
| Parse success rate (has date+time) | > 90% |
| Auth completion rate (started → connected) | > 80% |

---

## Part 2 — Product Requirements Document (PRD)

### 2.1 User Personas

**Persona A — "The Busy Professional" (primary)**
- Receives 10–30 Telegram event announcements per week
- Uses Google Calendar as their primary scheduling tool
- Doesn't want to leave Telegram to add events
- Speaks Russian or Uzbek

**Persona B — "The Community Manager"**
- Manages event channels; forwards their own posts to the bot
- Values speed over precision — happy to confirm a parsed result
- May use the bot dozens of times per day

### 2.2 User Journey

```
New user:
  /start → choose language → enter name → (optional) share phone → /auth → connect Google Calendar

Returning user — text/forwarded message:
  paste / forward message → bot parses → preview shown → [✅ Add] or [❌ Cancel] → event created → link returned

Returning user — voice message:
  record voice → bot transcribes → bot parses → same preview flow as above
```

### 2.3 Feature Requirements

#### FR-01: User Registration
| ID | Requirement | Priority |
|---|---|---|
| FR-01.1 | `/start` triggers language selection (EN / RU / UZ) for new users | Must Have |
| FR-01.2 | After language selection, bot asks for user's name | Must Have |
| FR-01.3 | After name, bot optionally asks for phone number (shareable via contact button or skippable) | Should Have |
| FR-01.4 | Returning users see a welcome-back message on `/start` | Must Have |
| FR-01.5 | User data (name, language, timezone, phone) persisted in SQLite | Must Have |

#### FR-02: Google Calendar Authentication
| ID | Requirement | Priority |
|---|---|---|
| FR-02.1 | `/auth` generates a unique OAuth URL and sends it to the user | Must Have |
| FR-02.2 | OAuth callback is handled by the embedded aiohttp server | Must Have |
| FR-02.3 | On successful auth, user is notified in Telegram | Must Have |
| FR-02.4 | Per-user tokens stored in SQLite; auto-refreshed on expiry | Must Have |
| FR-02.5 | Stale/unrefreshable tokens are deleted; user prompted to re-auth | Must Have |
| FR-02.6 | `/auth` on an already-connected account shows a confirmation message | Should Have |

#### FR-03: Text / Forwarded Message Parsing
| ID | Requirement | Priority |
|---|---|---|
| FR-03.1 | Bot accepts plain text, forwarded messages, and photo/document captions | Must Have |
| FR-03.2 | Claude AI extracts: title, date, start time, end time, location, description | Must Have |
| FR-03.3 | If `end_time` is absent, default to `start_time + 1 hour` | Must Have |
| FR-03.4 | If no event with a date/time is found, inform user clearly | Must Have |
| FR-03.5 | Preview message shown with formatted event details and Confirm/Cancel buttons | Must Have |
| FR-03.6 | Confirm creates the event in the user's primary Google Calendar | Must Have |
| FR-03.7 | On success, return a direct HTML link to the created event | Must Have |
| FR-03.8 | Cancel dismisses the pending event cleanly | Must Have |

#### FR-04: Voice Message Support
| ID | Requirement | Priority |
|---|---|---|
| FR-04.1 | Bot accepts Telegram voice messages (OGG/Opus) | Must Have |
| FR-04.2 | Audio transcribed via Google Gemini (`gemini-2.5-flash`) | Must Have |
| FR-04.3 | Transcribed text shown to user before parse result | Should Have |
| FR-04.4 | Transcribed text fed into the same parsing pipeline as FR-03 | Must Have |
| FR-04.5 | Temp audio file deleted from local disk after transcription | Must Have |

#### FR-05: Internationalisation (i18n)
| ID | Requirement | Priority |
|---|---|---|
| FR-05.1 | All user-facing strings available in English, Russian, Uzbek | Must Have |
| FR-05.2 | Language auto-detected from Telegram `language_code` during onboarding | Should Have |
| FR-05.3 | `/lang` command lets any user change their language at any time | Must Have |
| FR-05.4 | Language preference persisted per-user in the database | Must Have |

#### FR-06: Commands
| Command | Behaviour | Priority |
|---|---|---|
| `/start` | Registration for new users; welcome-back for existing | Must Have |
| `/auth` | Initiates Google OAuth flow | Must Have |
| `/help` | Shows command list and usage instructions | Must Have |
| `/lang` | Shows language picker keyboard | Must Have |

### 2.4 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | Bot must not block the Telegram event loop — all sync I/O via `asyncio.to_thread()` |
| NFR-02 | SQLite with WAL mode; each DB function opens/closes its own connection (thread-safe) |
| NFR-03 | OAuth state tokens expire after 10 minutes; cleaned up every 10 minutes via job queue |
| NFR-04 | Bot token and API keys loaded from `.env`; never hardcoded |
| NFR-05 | Internal error details must not be exposed to end users |
| NFR-06 | Pending events stored in `context.user_data` (in-memory); lost on bot restart |

### 2.5 Data Model

```
users
  telegram_id   INTEGER PK
  name          TEXT
  username      TEXT (nullable)
  phone         TEXT (nullable)
  timezone      TEXT DEFAULT 'Europe/Moscow'
  language      TEXT DEFAULT 'en'
  created_at    TEXT

google_tokens
  telegram_id   INTEGER PK → users
  token_json    TEXT (Google OAuth credential JSON)
  updated_at    TEXT

oauth_states
  state         TEXT PK (UUID)
  telegram_id   INTEGER
  code_verifier TEXT (nullable, PKCE)
  created_at    TEXT (auto-expires in 10 min)
```

### 2.6 Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | `python-telegram-bot 21.3` |
| AI parsing | Anthropic Claude (`claude-sonnet-4-6`) |
| Voice transcription | Google Gemini (`gemini-2.5-flash`) |
| Calendar integration | Google Calendar API v3 |
| OAuth callback server | `aiohttp` (embedded, port 8080) |
| Telegram notifications from OAuth | `httpx` |
| Database | SQLite (WAL mode) |
| Language | Python 3.11+ |

### 2.7 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | From @BotFather |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `GOOGLE_CLIENT_SECRETS_PATH` | Yes | `credentials/client_secrets_web.json` | OAuth Web client secrets |
| `OAUTH_REDIRECT_URI` | Yes | `https://calbot.nawys.uz/oauth/callback` | Public redirect URI |
| `OAUTH_SERVER_PORT` | No | `8080` | Port for embedded OAuth server |
| `TIMEZONE` | No | `Europe/Moscow` | Default IANA timezone for new users |
| `DATABASE_PATH` | No | `data/bot.db` | SQLite database file path |

### 2.8 Known Limitations & Future Work

| Item | Notes |
|---|---|
| Pending events lost on restart | Acceptable for v1; could persist to DB in future |
| No event editing before confirm | Only confirm/cancel supported today |
| No recurring events | Single-occurrence events only |
| PKCE flow cosmetically present | Code verifier stored but not sent to Google in auth URL — needs fix |
| Naive local time for date context | Claude receives server local time, not user's timezone — can cause wrong date for evening events |
| Gemini files not cleaned up | Uploaded audio files persist on Gemini account — needs `files.delete()` call |
