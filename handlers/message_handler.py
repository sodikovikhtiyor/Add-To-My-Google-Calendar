from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta

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
from services.ai_parser import apply_changes, parse_event_from_image, parse_intent
from services.calendar_service import (
    create_event,
    delete_event,
    find_matching_events,
    get_event,
    is_authenticated,
    update_event,
)
from services.transcription_service import transcribe_audio

logger = logging.getLogger(__name__)

_PENDING_KEY = "pending_event"
_PENDING_UPDATE_KEY = "pending_update"
_PENDING_UPDATE_INTENT_KEY = "pending_update_intent"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_lang(user: dict | None, update: Update | None = None) -> str:
    if user and user.get("language"):
        return user["language"]
    if update:
        return detect_language(update.effective_user.language_code)
    return "en"


async def _get_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if context.user_data.get("detected_lang"):
        return context.user_data["detected_lang"]
    telegram_id = update.effective_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    return _user_lang(user, update)


async def _check_user_ready(update, telegram_id: int) -> bool:
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user, update)

    if not user:
        await update.message.reply_text(get_text("not_registered", lang))
        return False

    if not await asyncio.to_thread(is_authenticated, telegram_id):
        await update.message.reply_text(get_text("calendar_not_connected", lang))
        return False

    return True


def _result_to_event(data: dict) -> Event | None:
    """Convert a 'create' intent dict from parse_intent into an Event object."""
    try:
        date_str = data["date"]
        start_dt = datetime.strptime(f"{date_str} {data['start_time']}", "%Y-%m-%d %H:%M")
        end_dt = (
            datetime.strptime(f"{date_str} {data['end_time']}", "%Y-%m-%d %H:%M")
            if data.get("end_time")
            else start_dt + timedelta(hours=1)
        )
        return Event(
            title=data["title"],
            start_dt=start_dt,
            end_dt=end_dt,
            location=data.get("location"),
            description=data.get("description"),
        )
    except (KeyError, ValueError):
        return None


def _dict_to_event(event_dict: dict) -> Event:
    """Convert a Google Calendar API event dict to an Event object."""
    start_str = (event_dict.get("start") or {}).get("dateTime", "")
    end_str = (event_dict.get("end") or {}).get("dateTime", "")
    start_dt = datetime.fromisoformat(start_str).replace(tzinfo=None)
    end_dt = datetime.fromisoformat(end_str).replace(tzinfo=None)
    return Event(
        title=event_dict.get("summary", ""),
        start_dt=start_dt,
        end_dt=end_dt,
        location=event_dict.get("location"),
        description=event_dict.get("description"),
        event_id=event_dict.get("id"),
    )


def _format_event_button_label(event_dict: dict) -> str:
    title = (event_dict.get("summary") or "Event")[:30]
    start_str = (event_dict.get("start") or {}).get("dateTime", "")
    if start_str:
        try:
            dt = datetime.fromisoformat(start_str).replace(tzinfo=None)
            return f"{title} — {dt.strftime('%d %b %H:%M')}"
        except ValueError:
            pass
    return title


def _format_preview(event: Event, lang: str = "en") -> str:
    lines = [
        f"*{event.title}*",
        f"\U0001f4c5 {event.start_dt.strftime('%A, %d %B %Y')}",
        f"⏰ {event.start_dt.strftime('%H:%M')} – {event.end_dt.strftime('%H:%M')}",
    ]
    if event.location:
        lines.append(f"\U0001f4cd {event.location}")
    if event.description:
        lines.append(f"\U0001f4dd {event.description}")
    lines.append(get_text("preview_footer", lang))
    return "\n".join(lines)


def _format_update_preview(original: Event, updated: Event, lang: str) -> str:
    lines = [get_text("update_preview_header", lang), ""]
    lines.append(f"*{updated.title}*")
    lines.append(f"\U0001f4c5 {updated.start_dt.strftime('%A, %d %B %Y')}")
    lines.append(f"⏰ {updated.start_dt.strftime('%H:%M')} – {updated.end_dt.strftime('%H:%M')}")
    if updated.location:
        lines.append(f"\U0001f4cd {updated.location}")
    if updated.description:
        lines.append(f"\U0001f4dd {updated.description}")

    changes_desc = []
    if original.title != updated.title:
        changes_desc.append(f"• Title: {original.title} → {updated.title}")
    if original.start_dt.date() != updated.start_dt.date():
        changes_desc.append(
            f"• Date: {original.start_dt.strftime('%d %b')} → {updated.start_dt.strftime('%d %b')}"
        )
    orig_time = f"{original.start_dt.strftime('%H:%M')}–{original.end_dt.strftime('%H:%M')}"
    new_time = f"{updated.start_dt.strftime('%H:%M')}–{updated.end_dt.strftime('%H:%M')}"
    if orig_time != new_time:
        changes_desc.append(f"• Time: {orig_time} → {new_time}")
    if original.location != updated.location:
        changes_desc.append(f"• Location: {updated.location or '(removed)'}")
    if original.description != updated.description and updated.description:
        changes_desc.append("• Note updated")

    if changes_desc:
        lines.append("")
        lines.append("_Changes:_")
        lines.extend(changes_desc)

    return "\n".join(lines)


def _format_delete_preview(event: Event, lang: str) -> str:
    lines = [
        get_text("delete_preview", lang),
        "",
        f"*{event.title}*",
        f"\U0001f4c5 {event.start_dt.strftime('%A, %d %B %Y')}",
        f"⏰ {event.start_dt.strftime('%H:%M')} – {event.end_dt.strftime('%H:%M')}",
    ]
    if event.location:
        lines.append(f"\U0001f4cd {event.location}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Update / delete intent handlers (called from _process_event_text)
# ---------------------------------------------------------------------------

async def _handle_update_intent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parsed: dict,
    status_msg,
    lang: str,
) -> None:
    telegram_id = update.effective_user.id
    search = parsed.get("search", {})
    changes = parsed.get("changes", {})

    await status_msg.edit_text(get_text("update_searching", lang))

    try:
        matches = await asyncio.to_thread(
            find_matching_events,
            telegram_id,
            search.get("title_hint", ""),
            search.get("date"),
            search.get("start_time"),
        )
    except Exception as e:
        logger.error("Calendar search error: %s", e)
        await status_msg.edit_text(get_text("parse_error", lang, error=e))
        return

    if not matches:
        await status_msg.edit_text(get_text("update_no_match", lang))
        return

    if len(matches) == 1:
        event_dict = matches[0]
        new_event = apply_changes(event_dict, changes)
        original_event = _dict_to_event(event_dict)
        context.user_data[_PENDING_UPDATE_KEY] = {
            "event_id": event_dict["id"],
            "new_event": new_event,
            "original": original_event,
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("confirm_update_btn", lang), callback_data="confirm_update"),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]])
        await status_msg.edit_text(
            _format_update_preview(original_event, new_event, lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    else:
        context.user_data[_PENDING_UPDATE_INTENT_KEY] = {"changes": changes}
        buttons = [
            [InlineKeyboardButton(_format_event_button_label(e), callback_data=f"select_update:{e['id']}")]
            for e in matches[:5]
        ]
        buttons.append([InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel")])
        await status_msg.edit_text(
            get_text("update_multiple_matches", lang, count=len(matches)),
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def _handle_delete_intent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parsed: dict,
    status_msg,
    lang: str,
) -> None:
    telegram_id = update.effective_user.id
    search = parsed.get("search", {})

    await status_msg.edit_text(get_text("update_searching", lang))

    try:
        matches = await asyncio.to_thread(
            find_matching_events,
            telegram_id,
            search.get("title_hint", ""),
            search.get("date"),
            search.get("start_time"),
        )
    except Exception as e:
        logger.error("Calendar search error: %s", e)
        await status_msg.edit_text(get_text("parse_error", lang, error=e))
        return

    if not matches:
        await status_msg.edit_text(get_text("update_no_match", lang))
        return

    if len(matches) == 1:
        event_dict = matches[0]
        original_event = _dict_to_event(event_dict)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                get_text("confirm_delete_btn", lang),
                callback_data=f"confirm_delete:{event_dict['id']}",
            ),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]])
        await status_msg.edit_text(
            _format_delete_preview(original_event, lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    else:
        buttons = [
            [InlineKeyboardButton(_format_event_button_label(e), callback_data=f"select_delete:{e['id']}")]
            for e in matches[:5]
        ]
        buttons.append([InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel")])
        await status_msg.edit_text(
            get_text("update_multiple_matches", lang, count=len(matches)),
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ---------------------------------------------------------------------------
# Shared pipeline: text -> Claude parse -> route on intent
# ---------------------------------------------------------------------------

async def _process_event_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    status_msg,
) -> None:
    lang = await _get_lang(update, context)

    try:
        result = await asyncio.to_thread(parse_intent, text)
    except Exception as e:
        logger.error("AI parser error: %s", e)
        await status_msg.edit_text(get_text("parse_error", lang, error=e))
        return

    if result is None or "error" in result:
        await status_msg.edit_text(get_text("no_event_found", lang))
        return

    intent = result.get("intent", "create")

    if intent == "create":
        event = _result_to_event(result)
        if event is None:
            await status_msg.edit_text(get_text("no_event_found", lang))
            return
        context.user_data[_PENDING_KEY] = event
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("btn_confirm", lang), callback_data="confirm"),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]])
        await status_msg.edit_text(
            _format_preview(event, lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif intent == "update":
        await _handle_update_intent(update, context, result, status_msg, lang)

    elif intent == "delete":
        await _handle_delete_intent(update, context, result, status_msg, lang)

    else:
        await status_msg.edit_text(get_text("no_event_found", lang))


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id

    # ── Name registration intercept ──
    if context.user_data.get("awaiting_name"):
        lang = context.user_data.get("detected_lang", "en")
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text(get_text("name_empty", lang))
            return

        tz = os.getenv("TIMEZONE", "Europe/Moscow")
        username = update.effective_user.username
        await asyncio.to_thread(
            database.create_user, telegram_id, name, tz, username, lang
        )
        context.user_data.pop("awaiting_name", None)

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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id

    if not await _check_user_ready(update, telegram_id):
        return

    lang = await _get_lang(update, context)
    status = await update.message.reply_text(get_text("reading_photo", lang))

    photo = update.message.photo[-1]
    try:
        file = await photo.get_file()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
    except Exception as e:
        logger.error("Photo download error: %s", e)
        await status.edit_text(get_text("photo_download_error", lang, error=e))
        return

    try:
        with open(tmp_path, "rb") as f:
            image_bytes = f.read()
        caption = update.message.caption
        event = await asyncio.to_thread(parse_event_from_image, image_bytes, caption=caption)
    except Exception as e:
        logger.error("AI vision parser error: %s", e)
        await status.edit_text(get_text("parse_error", lang, error=e))
        return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if event is None:
        await status.edit_text(get_text("no_event_found", lang))
        return

    context.user_data[_PENDING_KEY] = event

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(get_text("btn_confirm", lang), callback_data="confirm"),
        InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
    ]])
    await status.edit_text(
        _format_preview(event, lang),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id

    if not await _check_user_ready(update, telegram_id):
        return

    lang = await _get_lang(update, context)
    status = await update.message.reply_text(get_text("transcribing", lang))

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

    await _process_event_text(update, context, text, status)


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user)

    if query.data == "cancel":
        context.user_data.pop(_PENDING_KEY, None)
        context.user_data.pop(_PENDING_UPDATE_KEY, None)
        context.user_data.pop(_PENDING_UPDATE_INTENT_KEY, None)
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


async def handle_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle selection of an event from a multiple-matches list (select_update: / select_delete:)."""
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user)

    action, event_id = query.data.split(":", 1)

    try:
        event_dict = await asyncio.to_thread(get_event, telegram_id, event_id)
    except Exception as e:
        logger.error("Failed to fetch event %s: %s", event_id, e)
        await query.edit_message_text(get_text("parse_error", lang, error=e))
        return

    if action == "select_update":
        intent = context.user_data.pop(_PENDING_UPDATE_INTENT_KEY, {})
        changes = intent.get("changes", {})
        new_event = apply_changes(event_dict, changes)
        original_event = _dict_to_event(event_dict)
        context.user_data[_PENDING_UPDATE_KEY] = {
            "event_id": event_id,
            "new_event": new_event,
            "original": original_event,
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("confirm_update_btn", lang), callback_data="confirm_update"),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]])
        await query.edit_message_text(
            _format_update_preview(original_event, new_event, lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif action == "select_delete":
        original_event = _dict_to_event(event_dict)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                get_text("confirm_delete_btn", lang),
                callback_data=f"confirm_delete:{event_id}",
            ),
            InlineKeyboardButton(get_text("btn_cancel", lang), callback_data="cancel"),
        ]])
        await query.edit_message_text(
            _format_delete_preview(original_event, lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


async def handle_update_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the confirm_update callback."""
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user)

    pending = context.user_data.pop(_PENDING_UPDATE_KEY, None)
    if pending is None:
        await query.edit_message_text(get_text("session_expired", lang))
        return

    await query.edit_message_text(get_text("updating_event", lang))

    try:
        link = await asyncio.to_thread(
            update_event, pending["event_id"], pending["new_event"], telegram_id
        )
        await query.edit_message_text(
            get_text("event_updated", lang, link=link),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Calendar update error: %s", e)
        await query.edit_message_text(get_text("update_error", lang, error=e))


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the confirm_delete:EVENT_ID callback."""
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    user = await asyncio.to_thread(database.get_user, telegram_id)
    lang = _user_lang(user)

    event_id = query.data.split(":", 1)[1]

    await query.edit_message_text(get_text("deleting_event", lang))

    try:
        await asyncio.to_thread(delete_event, event_id, telegram_id)
        await query.edit_message_text(get_text("event_deleted", lang))
    except Exception as e:
        logger.error("Calendar delete error: %s", e)
        await query.edit_message_text(get_text("delete_error", lang, error=e))


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
