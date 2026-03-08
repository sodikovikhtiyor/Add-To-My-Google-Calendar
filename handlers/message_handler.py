import asyncio
import logging
import os
import tempfile

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes

import database
from locales import detect_language, get_text
from models.event import Event
from services.ai_parser import parse_event
from services.calendar_service import create_event, is_authenticated
from services.transcription_service import transcribe_audio

logger = logging.getLogger(__name__)

_PENDING_KEY = "pending_event"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_lang(user: dict | None, update: Update | None = None) -> str:
    """Get user's language from DB, or detect from Telegram."""
    if user and user.get("language"):
        return user["language"]
    if update:
        return detect_language(update.effective_user.language_code)
    return "en"


async def _get_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get the language for the current user, checking context first, then DB."""
    # During registration, language is stored in context before user is in DB
    if context.user_data.get("detected_lang"):
        return context.user_data["detected_lang"]
    telegram_id = update.effective_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    return _user_lang(user, update)


async def _check_user_ready(update, telegram_id: int) -> bool:
    """Check that the user is registered and has Google Calendar connected.
    Sends an appropriate message if not. Returns True if ready."""
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user, update)

    if not user:
        await update.message.reply_text(get_text("not_registered", lang))
        return False

    if not await asyncio.to_thread(is_authenticated, telegram_id):
        await update.message.reply_text(get_text("calendar_not_connected", lang))
        return False

    return True


# ---------------------------------------------------------------------------
# Shared pipeline: text -> Claude parse -> preview keyboard
# ---------------------------------------------------------------------------

async def _process_event_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    status_msg,
) -> None:
    """Parse text with Claude AI and show an event preview with confirm/cancel."""
    lang = await _get_lang(update, context)

    try:
        event = await asyncio.to_thread(parse_event, text)
    except Exception as e:
        logger.error("AI parser error: %s", e)
        await status_msg.edit_text(get_text("parse_error", lang, error=e))
        return

    if event is None:
        await status_msg.edit_text(get_text("no_event_found", lang))
        return

    context.user_data[_PENDING_KEY] = event

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(get_text("btn_confirm", lang), callback_data="confirm"),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]
    ])
    await status_msg.edit_text(
        _format_preview(event, lang),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages and photo/document captions."""
    telegram_id = update.effective_user.id

    # ── Name registration intercept ──
    if context.user_data.get("awaiting_name"):
        lang = context.user_data.get("detected_lang", "en")
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text(get_text("name_empty", lang))
            return

        tz = os.getenv("TIMEZONE", "Europe/Moscow")
        username = update.effective_user.username  # may be None
        await asyncio.to_thread(
            database.create_user, telegram_id, name, tz, username, lang
        )
        context.user_data.pop("awaiting_name", None)

        # Ask for phone number
        context.user_data["awaiting_phone"] = True
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(get_text("btn_share_phone", lang), request_contact=True)],
             [KeyboardButton(get_text("btn_skip", lang))]],
            one_time_keyboard=True,
            resize_keyboard=True,
        )
        await update.message.reply_text(
            get_text("ask_phone", lang, name=name),
            reply_markup=keyboard,
        )
        return

    # ── Phone skip intercept ──
    if context.user_data.get("awaiting_phone"):
        lang = await _get_lang(update, context)
        text_input = (update.message.text or "").strip().lower()
        # Check against all language variants of "skip"
        skip_texts = {
            get_text("btn_skip", "en").lower(),
            get_text("btn_skip", "ru").lower(),
            get_text("btn_skip", "uz").lower(),
        }
        if text_input in skip_texts:
            context.user_data.pop("awaiting_phone", None)
            context.user_data.pop("detected_lang", None)
            await update.message.reply_text(
                get_text("phone_skipped", lang),
                reply_markup=ReplyKeyboardRemove(),
            )
            return

    # ── Normal event flow ──
    text = update.message.text or update.message.caption
    if not text:
        return

    if not await _check_user_ready(update, telegram_id):
        return

    lang = await _get_lang(update, context)
    status = await update.message.reply_text(get_text("parsing", lang))
    await _process_event_text(update, context, text, status)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages: transcribe with Gemini, then parse with Claude."""
    telegram_id = update.effective_user.id

    if not await _check_user_ready(update, telegram_id):
        return

    lang = await _get_lang(update, context)
    status = await update.message.reply_text(get_text("transcribing", lang))

    # Download voice file to a temporary location
    voice = update.message.voice
    try:
        file = await voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
    except Exception as e:
        logger.error("Voice download error: %s", e)
        await status.edit_text(get_text("voice_download_error", lang, error=e))
        return

    # Transcribe with Gemini
    try:
        text = await asyncio.to_thread(transcribe_audio, tmp_path)
    except Exception as e:
        logger.error("Transcription error: %s", e)
        await status.edit_text(get_text("transcribe_error", lang, error=e))
        return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    logger.info("Voice transcription result: %s", text)
    await status.edit_text(
        get_text("transcribed", lang, text=text),
        parse_mode="Markdown",
    )

    # Feed transcribed text into the shared pipeline
    await _process_event_text(update, context, text, status)


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user)

    if query.data == "cancel":
        context.user_data.pop(_PENDING_KEY, None)
        await query.edit_message_text(get_text("cancelled", lang))
        return

    event: Event | None = context.user_data.pop(_PENDING_KEY, None)
    if event is None:
        await query.edit_message_text(get_text("session_expired", lang))
        return

    await query.edit_message_text(get_text("adding_to_calendar", lang))

    try:
        link = await asyncio.to_thread(create_event, event, telegram_id)
        await query.edit_message_text(
            get_text("event_added", lang, link=link),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Calendar create error: %s", e)
        await query.edit_message_text(get_text("event_create_error", lang, error=e))


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared contact (phone number) during registration."""
    telegram_id = update.effective_user.id
    contact = update.message.contact

    if not contact or not contact.phone_number:
        return

    lang = await _get_lang(update, context)

    await asyncio.to_thread(database.update_user_phone, telegram_id, contact.phone_number)
    context.user_data.pop("awaiting_phone", None)
    context.user_data.pop("detected_lang", None)

    await update.message.reply_text(
        get_text("phone_saved", lang),
        reply_markup=ReplyKeyboardRemove(),
    )


def _format_preview(event: Event, lang: str = "en") -> str:
    lines = [
        f"*{event.title}*",
        f"\U0001f4c5 {event.start_dt.strftime('%A, %d %B %Y')}",
        f"\u23f0 {event.start_dt.strftime('%H:%M')} \u2013 {event.end_dt.strftime('%H:%M')}",
    ]
    if event.location:
        lines.append(f"\U0001f4cd {event.location}")
    if event.description:
        lines.append(f"\U0001f4dd {event.description}")
    lines.append(get_text("preview_footer", lang))
    return "\n".join(lines)
