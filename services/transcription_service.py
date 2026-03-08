import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

logger = logging.getLogger(__name__)

_client = None
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _get_client():
    global _client
    if _client is None:
        load_dotenv(_ENV_PATH, override=True)
        api_key = os.environ.get("GEMINI_API_KEY", "")
        logger.info("Initializing Gemini client (key length: %d)", len(api_key))
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is empty. "
                f"Checked os.environ and {_ENV_PATH}. "
                "Make sure the key is set in your .env file."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file using Google Gemini API.
    Accepts OGG/Opus files directly. Returns the transcribed text.
    Raises RuntimeError if transcription produces empty text.
    """
    client = _get_client()

    audio_file = client.files.upload(file=file_path)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            audio_file,
            "Transcribe this audio exactly as spoken. "
            "Return ONLY the transcription text, nothing else.",
        ],
    )

    text = response.text.strip()
    if not text:
        raise RuntimeError("Transcription returned empty text")

    logger.info("Transcribed audio (%s): %s", file_path, text[:200])
    return text
