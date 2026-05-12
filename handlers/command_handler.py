from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import database
from locales import detect_language, get_text
from services.calendar_service import is_authenticated

logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "6507257671"))


def _build_oauth_url(state: str) -> tuple[str, str | None]:
    """Build the Google OAuth authorization URL with the given state parameter.

    Returns (auth_url, code_verifier). The code_verifier is needed for PKCE
    and must be stored alongside the state for use during token exchange.
    """
    from google_auth_oauthlib.flow import Flow

    secrets_path = os.getenv(
        "GOOGLE_CLIENT_SECRETS_PATH", "credentials/client_secrets_web.json"
    )
    redirect_uri = os.getenv(
        "OAUTH_REDIRECT_URI", "https://calbot.nawys.uz/oauth/callback"
    )

    # Load client secrets and determine the key ("web" or "installed")
    with open(secrets_path) as f:
        client_config = json.load(f)

    flow = Flow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    # flow.code_verifier is set by authorization_url() for PKCE
    return auth_url, getattr(flow, "code_verifier", None)


def _lang_keyboard(prefix: str = "lang") -> InlineKeyboardMarkup:
    """Build the 3-button language selection keyboard.

    prefix: 'start_lang' for registration flow, 'lang' for /lang command.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                get_text("lang_btn_en", "en"), callback_data=f"{prefix}:en"
            ),
            InlineKeyboardButton(
                get_text("lang_btn_ru", "en"), callback_data=f"{prefix}:ru"
            ),
            InlineKeyboardButton(
                get_text("lang_btn_uz", "en"), callback_data=f"{prefix}:uz"
            ),
        ]
    ])


def _user_lang(user: dict | None, update: Update | None = None) -> str:
    """Get user's language from DB, or detect from Telegram if not registered yet."""
    if user and user.get("language"):
        return user["language"]
    if update:
        return detect_language(update.effective_user.language_code)
    return "en"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)

    if user:
        lang = _user_lang(user)
        await update.message.reply_text(
            get_text("welcome_back", lang, name=user["name"])
        )
    else:
        # New user — show language picker first
        lang = detect_language(update.effective_user.language_code)
        await update.message.reply_text(
            get_text("welcome_choose_lang", lang),
            reply_markup=_lang_keyboard("start_lang"),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user, update)

    await update.message.reply_text(
        get_text("help_text", lang),
        parse_mode="Markdown",
    )


async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id

    # Must be registered first
    user = await asyncio.to_thread(database.get_user, telegram_id)
    if not user:
        lang = detect_language(update.effective_user.language_code)
        await update.message.reply_text(get_text("not_registered", lang))
        return

    lang = _user_lang(user)

    # Already connected?
    if await asyncio.to_thread(is_authenticated, telegram_id):
        await update.message.reply_text(get_text("auth_already_connected", lang))
        return

    # Generate OAuth URL
    state = str(uuid.uuid4())

    try:
        oauth_url, code_verifier = _build_oauth_url(state)
    except Exception as e:
        logger.error("Failed to build OAuth URL: %s", e)
        await update.message.reply_text(
            get_text("auth_link_error", lang, error=e)
        )
        return

    # Store state + code_verifier for PKCE token exchange
    await asyncio.to_thread(database.create_oauth_state, state, telegram_id, code_verifier)

    await update.message.reply_text(
        get_text("auth_link", lang, url=oauth_url),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ── /lang command ────────────────────────────────────────

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language selection keyboard."""
    telegram_id = update.effective_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user, update)

    await update.message.reply_text(
        get_text("lang_prompt", lang),
        reply_markup=_lang_keyboard("lang"),
    )


# ── Admin commands ──────────────────────────────────────

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: list all registered users."""
    if update.effective_user.id != ADMIN_ID:
        return

    users = await asyncio.to_thread(database.list_users)
    if not users:
        await update.message.reply_text("No users registered.")
        return

    lines = ["<b>Registered users:</b>\n"]
    for u in users:
        username = f"@{u['username']}" if u["username"] else "—"
        lines.append(
            f"• <code>{u['telegram_id']}</code> | {u['name']} | {username} | {u['language']} | {u['created_at'][:10]}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: /delete_user <telegram_id>"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /delete_user <telegram_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID — must be a number.")
        return

    existed = await asyncio.to_thread(database.delete_user, target_id)
    if existed:
        await update.message.reply_text(f"User <code>{target_id}</code> deleted.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"User <code>{target_id}</code> not found.", parse_mode="HTML")


# ── Callback handlers ───────────────────────────────────

async def handle_start_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection during /start registration.

    After user picks a language, ask for their name.
    """
    query = update.callback_query
    await query.answer()

    chosen_lang = query.data.split(":")[1]  # "start_lang:ru" → "ru"

    # Store chosen language in context for the name-registration step
    context.user_data["awaiting_name"] = True
    context.user_data["detected_lang"] = chosen_lang

    await query.edit_message_text(get_text("welcome_new", chosen_lang))


async def handle_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection from /lang command (existing user)."""
    query = update.callback_query
    await query.answer()

    chosen_lang = query.data.split(":")[1]  # "lang:en" → "en"
    telegram_id = query.from_user.id

    await asyncio.to_thread(database.update_user_language, telegram_id, chosen_lang)
    await query.edit_message_text(get_text("lang_changed", chosen_lang))
