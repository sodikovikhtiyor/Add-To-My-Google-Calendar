"""
SQLite database access layer for multi-user Calendar Bot.

Tables:
  - users: Telegram user registration (name, username, phone, timezone)
  - google_tokens: Per-user Google OAuth credentials
  - oauth_states: Temporary state→telegram_id mapping for OAuth flow

Every public function opens and closes its own connection,
making them safe to call via asyncio.to_thread().
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH: str | None = None


def _db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = os.getenv("DATABASE_PATH", "data/bot.db")
    return _DB_PATH


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ──────────────────────────────────────────────

def init_db() -> None:
    """Create tables if they don't exist. Call once at startup."""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id  INTEGER PRIMARY KEY,
                name         TEXT NOT NULL,
                username     TEXT,
                phone        TEXT,
                timezone     TEXT NOT NULL DEFAULT 'Asia/Tashkent',
                language     TEXT NOT NULL DEFAULT 'en',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS google_tokens (
                telegram_id  INTEGER PRIMARY KEY REFERENCES users(telegram_id),
                token_json   TEXT NOT NULL,
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS oauth_states (
                state          TEXT PRIMARY KEY,
                telegram_id    INTEGER NOT NULL,
                code_verifier  TEXT,
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        logger.info("Database initialized at %s", _db_path())
    finally:
        conn.close()


# ── Users ───────────────────────────────────────────────

def create_user(
    telegram_id: int,
    name: str,
    timezone: str = "Asia/Tashkent",
    username: str | None = None,
    language: str = "en",
) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, name, username, timezone, language) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, name, username, timezone, language),
        )
        conn.commit()
        logger.info("Created user %d (%s, @%s, lang=%s)", telegram_id, name, username or "—", language)
    finally:
        conn.close()


def update_user_phone(telegram_id: int, phone: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET phone = ? WHERE telegram_id = ?",
            (phone, telegram_id),
        )
        conn.commit()
        logger.info("Saved phone for user %d", telegram_id)
    finally:
        conn.close()


def update_user_language(telegram_id: int, language: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET language = ? WHERE telegram_id = ?",
            (language, telegram_id),
        )
        conn.commit()
        logger.info("Updated language for user %d to %s", telegram_id, language)
    finally:
        conn.close()


def get_user(telegram_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT telegram_id, name, username, phone, timezone, language, created_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_user(telegram_id: int) -> bool:
    """Delete a user and their Google token. Returns True if the user existed."""
    conn = _connect()
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM google_tokens WHERE telegram_id = ?", (telegram_id,))
        result = conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        existed = result.rowcount > 0
        if existed:
            logger.info("Deleted user %d", telegram_id)
        return existed
    finally:
        conn.close()


def list_users() -> list[dict]:
    """Return all registered users."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT telegram_id, name, username, phone, language, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ── Google Tokens ───────────────────────────────────────

def save_google_token(telegram_id: int, token_json: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO google_tokens (telegram_id, token_json, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(telegram_id) DO UPDATE SET
                   token_json = excluded.token_json,
                   updated_at = datetime('now')""",
            (telegram_id, token_json),
        )
        conn.commit()
        logger.info("Saved Google token for user %d", telegram_id)
    finally:
        conn.close()


def get_google_token(telegram_id: int) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT token_json FROM google_tokens WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row["token_json"] if row else None
    finally:
        conn.close()


def delete_google_token(telegram_id: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM google_tokens WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()
        logger.info("Deleted Google token for user %d", telegram_id)
    finally:
        conn.close()


# ── OAuth States ────────────────────────────────────────

def create_oauth_state(state: str, telegram_id: int, code_verifier: str | None = None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO oauth_states (state, telegram_id, code_verifier) VALUES (?, ?, ?)",
            (state, telegram_id, code_verifier),
        )
        conn.commit()
    finally:
        conn.close()


def pop_oauth_state(state: str) -> Optional[dict]:
    """Return {telegram_id, code_verifier} for a state and delete it. Returns None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT telegram_id, code_verifier FROM oauth_states WHERE state = ?",
            (state,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
        return {"telegram_id": row["telegram_id"], "code_verifier": row["code_verifier"]}
    finally:
        conn.close()


def cleanup_expired_states(max_age_minutes: int = 10) -> None:
    conn = _connect()
    try:
        cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
        result = conn.execute(
            "DELETE FROM oauth_states WHERE created_at < ?",
            (cutoff,),
        )
        conn.commit()
        if result.rowcount:
            logger.info("Cleaned up %d expired OAuth states", result.rowcount)
    finally:
        conn.close()
