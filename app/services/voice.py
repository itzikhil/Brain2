"""Voice message transcription — Groq cloud with local Whisper fallback."""
import logging
import httpx
from faster_whisper import WhisperModel

from app.config import get_settings

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Load local Whisper model once (downloads ~1.5GB on first use)."""
    global _model
    if _model is None:
        logger.info("Loading faster-whisper 'medium' model...")
        _model = WhisperModel("medium", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


async def transcribe_with_groq(file_path: str) -> tuple[str, str]:
    """
    Transcribe via Groq cloud API (whisper-large-v3).

    Returns (text, language). Raises on failure.
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": ("voice.ogg", f, "audio/ogg")},
                data={
                    "model": "whisper-large-v3",
                    "response_format": "verbose_json",
                    "prompt": "שלום, hello, hallo. This conversation may be in Hebrew, English, or German.",
                },
            )
        resp.raise_for_status()
        data = resp.json()
        return data["text"], data.get("language", "unknown")


def _transcribe_local(file_path: str) -> tuple[str, str]:
    """Transcribe with local Whisper model."""
    model = _get_model()
    segments, info = model.transcribe(
        file_path,
        initial_prompt="שלום, hello, hallo. This conversation may be in Hebrew, English, or German.",
    )
    text = " ".join(segment.text.strip() for segment in segments)
    return text, info.language


async def transcribe_voice(file_path: str) -> tuple[str, str]:
    """
    Transcribe an audio file — tries Groq first, falls back to local Whisper.

    Returns (text, detected_language).
    """
    settings = get_settings()

    if settings.groq_api_key:
        try:
            text, language = await transcribe_with_groq(file_path)
            logger.info("🎤 Groq (cloud) transcription succeeded")
            return text, language
        except Exception as e:
            logger.warning(f"Groq transcription failed, falling back to local Whisper: {e}")

    text, language = _transcribe_local(file_path)
    logger.info("🎤 Whisper (local) transcription used")
    return text, language
