"""Voice message transcription using faster-whisper."""
import logging
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Load Whisper model once (downloads ~3GB on first use)."""
    global _model
    if _model is None:
        logger.info("Loading faster-whisper 'large-v3' model...")
        _model = WhisperModel("large-v3", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


def transcribe_voice(file_path: str) -> tuple[str, str]:
    """
    Transcribe an audio file and return (text, detected_language).

    Supports Hebrew, English, German and other languages.
    Uses an initial_prompt hint to bias detection toward Hebrew, English,
    and German without forcing a specific language.
    """
    model = _get_model()
    segments, info = model.transcribe(
        file_path,
        initial_prompt="שלום, hello, hallo. This conversation may be in Hebrew, English, or German.",
    )
    text = " ".join(segment.text.strip() for segment in segments)
    return text, info.language
