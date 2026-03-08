"""Uzbek translations for Calendar Bot."""

STRINGS: dict[str, str] = {
    # ── /start ────────────────────────────────────────────
    "welcome_back": (
        "Qaytganingizdan xursandmiz, {name}!\n\n"
        "Menga tadbir yuboring yoki /auth orqali Google Calendar ulanishini tekshiring."
    ),
    "welcome_choose_lang": "Xush kelibsiz! Tilni tanlang:",
    "welcome_new": (
        "Ajoyib! Men sizning shaxsiy kalendar yordamchingizman.\n\n"
        "Ismingiz nima?"
    ),

    # ── Registration ──────────────────────────────────────
    "name_empty": "Iltimos, ismingizni kiriting.",
    "ask_phone": (
        "Tanishganimdan xursandman, {name}!\n\n"
        "Telefon raqamingizni ulashmoqchimisiz?"
    ),
    "btn_share_phone": "\U0001f4f1 Raqamni yuborish",
    "btn_skip": "O\u2018tkazib yuborish",
    "phone_saved": (
        "\u2705 Telefon raqami saqlandi!\n\n"
        "Endi /auth orqali Google Calendar\u2019ni ulang."
    ),
    "phone_skipped": "Muammo yo\u2018q! /auth orqali Google Calendar\u2019ni ulang.",

    # ── /help ─────────────────────────────────────────────
    "help_text": (
        "*Buyruqlar*\n"
        "/start \u2014 ro\u2018yxatdan o\u2018tish yoki profil\n"
        "/auth \u2014 Google Calendar\u2019ni ulash\n"
        "/lang \u2014 tilni o\u2018zgartirish\n"
        "/help \u2014 ushbu xabarni ko\u2018rsatish\n\n"
        "*Foydalanish*\n"
        "1. /start orqali ro\u2018yxatdan o\u2018ting (ismingizni kiriting)\n"
        "2. /auth orqali Google Calendar\u2019ni ulang\n"
        "3. Tadbir ma\u2019lumotlari bilan xabar yuboring yoki yo\u2018llang "
        "(sarlavha, sana, vaqt, joy)\n"
        "4. Yoki tadbirni tasvirlovchi *ovozli xabar* yuboring\n\n"
        "Men ma\u2019lumotlarni ajratib olaman va kalendarga qo\u2018shishdan oldin "
        "tasdiqlashni so\u2018rayman."
    ),

    # ── /auth ─────────────────────────────────────────────
    "not_registered": "Avval /start orqali ro\u2018yxatdan o\u2018ting.",
    "auth_already_connected": "Google Calendar ulangan va tayyor!",
    "auth_link": (
        "Google Calendar\u2019ni ulash uchun quyidagi havolani bosing:\n\n"
        "[Google Calendar\u2019ni ulash]({url})\n\n"
        "Avtorizatsiyadan so\u2018ng siz qayta yo\u2018naltirilasiz "
        "va men ulanishni tasdiqlayman."
    ),
    "auth_link_error": "Avtorizatsiya havolasini yaratib bo\u2018lmadi: {error}",

    # ── Calendar not connected ────────────────────────────
    "calendar_not_connected": (
        "Google Calendar ulanmagan.\n"
        "Ulash uchun /auth buyrug\u2018ini ishlating."
    ),
    "calendar_not_connected_error": "Google Calendar ulanmagan. /auth orqali ulang.",

    # ── Event parsing ─────────────────────────────────────
    "parsing": "Tadbir ma\u2019lumotlarini tahlil qilmoqda\u2026",
    "parse_error": "Tahlil xatosi: {error}",
    "no_event_found": (
        "Ushbu xabarda tadbir topilmadi. "
        "Sana va vaqt ko\u2018rsatilganligiga ishonch hosil qiling."
    ),

    # ── Event preview & confirmation ──────────────────────
    "btn_confirm": "\u2705 Qo\u2018shish",
    "btn_cancel": "\u274c Bekor qilish",
    "preview_footer": "\nBu tadbirni Google Calendar\u2019ga qo\u2018shilsinmi?",
    "cancelled": "Bekor qilindi.",
    "session_expired": "Sessiya muddati tugadi \u2014 xabarni qayta yuboring.",
    "adding_to_calendar": "Google Calendar\u2019ga qo\u2018shilmoqda\u2026",
    "event_added": "Tadbir qo\u2018shildi! [Google Calendar\u2019da ochish]({link})",
    "event_create_error": "Tadbirni yaratib bo\u2018lmadi: {error}",

    # ── Voice messages ────────────────────────────────────
    "transcribing": "Audio tanib olinmoqda\u2026",
    "voice_download_error": "Ovozli xabarni yuklab bo\u2018lmadi: {error}",
    "transcribe_error": "Audioni tanib bo\u2018lmadi: {error}",
    "transcribed": "Tanib olindi: _{text}_\n\nTadbir ma\u2019lumotlarini tahlil qilmoqda\u2026",

    # ── OAuth callback (HTML pages) ───────────────────────
    "oauth_success_title": "Avtorizatsiya muvaffaqiyatli!",
    "oauth_success_msg": "Google Calendar muvaffaqiyatli ulandi.",
    "oauth_success_close": "Bu oynani yopib, Telegram\u2019ga qaytishingiz mumkin.",
    "oauth_error_title": "Avtorizatsiya xatosi",
    "oauth_error_retry": "Telegram\u2019ga qaytib, /auth buyrug\u2018ini qayta ishlating.",
    "oauth_connected": (
        "\u2705 Google Calendar muvaffaqiyatli ulandi!\n\n"
        "Boshlash uchun menga tadbir yuboring."
    ),

    # ── /lang ─────────────────────────────────────────────
    "lang_prompt": "Tilni tanlang:",
    "lang_changed": "Til o\u2018zbek tiliga o\u2018zgartirildi!",
    "lang_btn_en": "\U0001f1ec\U0001f1e7 English",
    "lang_btn_ru": "\U0001f1f7\U0001f1fa \u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "lang_btn_uz": "\U0001f1fa\U0001f1ff O\u2018zbekcha",
}
