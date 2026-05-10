import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Ensure .env is found regardless of working directory
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
from handlers.command_handler import (
    admin_delete_user,
    admin_list_users,
    auth_check,
    handle_lang_callback,
    handle_start_lang_callback,
    help_command,
    lang_command,
    start,
)
from handlers.message_handler import handle_confirmation, handle_contact, handle_message, handle_photo, handle_voice
from web.oauth_server import start_oauth_server, stop_oauth_server

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Lifecycle hooks ─────────────────────────────────────

async def post_init(application: Application) -> None:
    """Called after Application.initialize() — start the OAuth callback server."""
    await start_oauth_server(application.bot.token)
    logger.info("OAuth server started via post_init")


async def post_shutdown(application: Application) -> None:
    """Called during shutdown — stop the OAuth callback server."""
    await stop_oauth_server()
    logger.info("OAuth server stopped via post_shutdown")


# ── Periodic tasks ──────────────────────────────────────

async def cleanup_states(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean up expired OAuth state tokens every 10 minutes."""
    await asyncio.to_thread(database.cleanup_expired_states)


# ── Main ────────────────────────────────────────────────

def main() -> None:
    # Initialize database
    database.init_db()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("auth", auth_check))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("list_users", admin_list_users))
    app.add_handler(CommandHandler("delete_user", admin_delete_user))
    app.add_handler(CallbackQueryHandler(handle_start_lang_callback, pattern=r"^start_lang:"))
    app.add_handler(CallbackQueryHandler(handle_lang_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(handle_confirmation))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | filters.CAPTION,
        handle_message,
    ))

    # Periodic cleanup of expired OAuth states (every 10 minutes)
    app.job_queue.run_repeating(cleanup_states, interval=600, first=60)

    logger.info("Bot is running")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
