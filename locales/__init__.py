"""
Lightweight i18n engine for Calendar Bot.

Usage:
    from locales import get_text, detect_language

    lang = detect_language(update.effective_user.language_code)
    text = get_text("welcome_new", lang)
    text = get_text("ask_phone", lang, name="Alice")
"""

from __future__ import annotations

import logging
from typing import Any

from locales.en import STRINGS as EN
from locales.ru import STRINGS as RU
from locales.uz import STRINGS as UZ

logger = logging.getLogger(__name__)

LANGUAGES: dict[str, dict[str, str]] = {
    "en": EN,
    "ru": RU,
    "uz": UZ,
}

DEFAULT_LANG = "en"
SUPPORTED_CODES = frozenset(LANGUAGES.keys())


def detect_language(language_code: str | None) -> str:
    """Map Telegram's language_code to a supported language.

    Telegram sends ISO 639-1 codes like "ru", "en", "uz", "uk", etc.
    We take the first two characters and check if they match.
    Falls back to English for unsupported languages.
    """
    if not language_code:
        return DEFAULT_LANG
    code = language_code.lower()[:2]
    if code in SUPPORTED_CODES:
        return code
    return DEFAULT_LANG


def get_text(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """Look up a translation string by key, with optional {placeholder} formatting.

    Falls back to English if the key is missing in the requested language.
    Falls back to the raw key if it's missing everywhere (should not happen).
    """
    strings = LANGUAGES.get(lang, EN)
    text = strings.get(key)

    # Fallback to English
    if text is None and lang != DEFAULT_LANG:
        text = EN.get(key)

    # Last resort — return the key itself
    if text is None:
        logger.warning("Missing translation key: %s (lang=%s)", key, lang)
        return key

    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError as e:
            logger.warning("Missing format arg %s for key %s", e, key)
            return text

    return text
