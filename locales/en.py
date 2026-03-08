"""English translations for Calendar Bot."""

STRINGS: dict[str, str] = {
    # ── /start ────────────────────────────────────────────
    "welcome_back": (
        "Welcome back, {name}!\n\n"
        "Send me an event or use /auth to check your Google Calendar connection."
    ),
    "welcome_choose_lang": "Welcome! Please choose your language:",
    "welcome_new": "Great! I'm your personal calendar assistant.\n\nWhat's your name?",

    # ── Registration ──────────────────────────────────────
    "name_empty": "Please enter your name.",
    "ask_phone": (
        "Nice to meet you, {name}!\n\n"
        "Would you like to share your phone number?"
    ),
    "btn_share_phone": "\U0001f4f1 Share phone number",
    "btn_skip": "Skip",
    "phone_saved": (
        "\u2705 Phone number saved!\n\n"
        "Now connect your Google Calendar with /auth."
    ),
    "phone_skipped": "No problem! Now connect your Google Calendar with /auth.",

    # ── /help ─────────────────────────────────────────────
    "help_text": (
        "*Commands*\n"
        "/start \u2014 register or see your profile\n"
        "/auth \u2014 connect your Google Calendar\n"
        "/lang \u2014 change language\n"
        "/help \u2014 show this message\n\n"
        "*Usage*\n"
        "1. Register with /start (enter your name)\n"
        "2. Connect your Google Calendar with /auth\n"
        "3. Forward or paste any message with event details "
        "(title, date, time, location)\n"
        "4. Or send a *voice message* describing an event\n\n"
        "I'll extract the details and ask for confirmation "
        "before adding to your calendar."
    ),

    # ── /auth ─────────────────────────────────────────────
    "not_registered": "Please register first with /start.",
    "auth_already_connected": "Google Calendar is connected and ready!",
    "auth_link": (
        "Click the link below to connect your Google Calendar:\n\n"
        "[Authorize Google Calendar]({url})\n\n"
        "After authorizing, you\u2019ll be redirected back "
        "and I\u2019ll confirm the connection."
    ),
    "auth_link_error": "Failed to generate authorization link: {error}",

    # ── Calendar not connected ────────────────────────────
    "calendar_not_connected": (
        "Google Calendar is not connected.\n"
        "Use /auth to connect your calendar."
    ),
    "calendar_not_connected_error": "Google Calendar is not connected. Use /auth to connect.",

    # ── Event parsing ─────────────────────────────────────
    "parsing": "Parsing event details\u2026",
    "parse_error": "Failed to parse: {error}",
    "no_event_found": (
        "No event found in this message. "
        "Make sure it includes a date and time."
    ),

    # ── Event preview & confirmation ──────────────────────
    "btn_confirm": "\u2705 Add to Calendar",
    "btn_cancel": "\u274c Cancel",
    "preview_footer": "\nAdd this event to Google Calendar?",
    "cancelled": "Cancelled.",
    "session_expired": "Session expired \u2014 please send the message again.",
    "adding_to_calendar": "Adding to Google Calendar\u2026",
    "event_added": "Event added! [Open in Google Calendar]({link})",
    "event_create_error": "Failed to create event: {error}",

    # ── Voice messages ────────────────────────────────────
    "transcribing": "Transcribing audio\u2026",
    "voice_download_error": "Failed to download voice message: {error}",
    "transcribe_error": "Failed to transcribe audio: {error}",
    "transcribed": "Transcribed: _{text}_\n\nParsing event details\u2026",

    # ── OAuth callback (HTML pages) ───────────────────────
    "oauth_success_title": "Authorization Successful!",
    "oauth_success_msg": "Your Google Calendar is now connected.",
    "oauth_success_close": "You can close this tab and return to Telegram.",
    "oauth_error_title": "Authorization Failed",
    "oauth_error_retry": "Please go back to Telegram and try /auth again.",
    "oauth_connected": (
        "\u2705 Google Calendar connected successfully!\n\n"
        "Send me an event to get started."
    ),

    # ── /lang ─────────────────────────────────────────────
    "lang_prompt": "Choose your language:",
    "lang_changed": "Language changed to English!",
    "lang_btn_en": "\U0001f1ec\U0001f1e7 English",
    "lang_btn_ru": "\U0001f1f7\U0001f1fa \u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "lang_btn_uz": "\U0001f1fa\U0001f1ff O\u2018zbekcha",
}
