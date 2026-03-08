import logging
import asyncio
from datetime import datetime
from typing import Optional, Literal
from telegram import Bot
from telegram.error import TelegramError

from app.config import get_settings

# Configure module logger
logger = logging.getLogger("external_brain")
logger.setLevel(logging.INFO)

# Console handler with formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Event type icons for Telegram messages
EVENT_ICONS = {
    "document": "📄",
    "memory": "🧠",
    "search": "🔍",
    "shopping": "🛒",
    "user": "👤",
    "error": "❌",
    "system": "⚙️",
    "ocr": "📷",
    "embedding": "🔢",
}

# Status icons
STATUS_ICONS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "pending": "⏳",
}


class BrainLogger:
    _instance = None
    _bot: Optional[Bot] = None
    _channel_id: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        """Initialize the logger with Telegram bot if configured."""
        if self._initialized:
            return

        settings = get_settings()

        if hasattr(settings, 'log_channel_id') and settings.log_channel_id:
            self._channel_id = settings.log_channel_id
            self._bot = Bot(token=settings.telegram_bot_token)
            logger.info(f"Telegram logging enabled for channel: {self._channel_id}")
        else:
            logger.info("Telegram logging disabled (no LOG_CHANNEL_ID)")

        self._initialized = True

    async def log_event(
        self,
        event_type: str,
        message: str,
        status: Literal["success", "error", "warning", "info", "pending"] = "info",
        user_id: Optional[int] = None,
        metadata: Optional[dict] = None
    ):
        """
        Log an event to console and optionally to Telegram channel.

        Args:
            event_type: Type of event (document, memory, search, etc.)
            message: Human-readable message
            status: Event status (success, error, warning, info, pending)
            user_id: Optional user ID for context
            metadata: Optional additional data
        """
        # Get icons
        event_icon = EVENT_ICONS.get(event_type, "📌")
        status_icon = STATUS_ICONS.get(status, "ℹ️")

        # Format console log
        log_level = logging.ERROR if status == "error" else logging.WARNING if status == "warning" else logging.INFO
        console_msg = f"[{event_type.upper()}] {status_icon} {message}"
        if user_id:
            console_msg += f" (user: {user_id})"
        logger.log(log_level, console_msg)

        # Send to Telegram channel if configured
        if self._bot and self._channel_id:
            await self._send_to_channel(event_type, event_icon, status_icon, message, user_id, metadata)

    async def _send_to_channel(
        self,
        event_type: str,
        event_icon: str,
        status_icon: str,
        message: str,
        user_id: Optional[int],
        metadata: Optional[dict]
    ):
        """Send formatted log message to Telegram channel."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build Telegram message
        lines = [
            f"{event_icon} **{event_type.upper()}** {status_icon}",
            f"`{timestamp}`",
            "",
            message,
        ]

        if user_id:
            lines.append(f"\n👤 User: `{user_id}`")

        if metadata:
            lines.append("\n📎 Details:")
            for key, value in metadata.items():
                # Truncate long values
                str_value = str(value)[:100]
                lines.append(f"  • {key}: `{str_value}`")

        telegram_msg = "\n".join(lines)

        try:
            await self._bot.send_message(
                chat_id=self._channel_id,
                text=telegram_msg,
                parse_mode="Markdown"
            )
        except TelegramError as e:
            logger.warning(f"Failed to send log to Telegram: {e}")


# Global logger instance
brain_logger = BrainLogger()


async def log_event(
    event_type: str,
    message: str,
    status: Literal["success", "error", "warning", "info", "pending"] = "info",
    user_id: Optional[int] = None,
    metadata: Optional[dict] = None
):
    """Convenience function for logging events."""
    brain_logger.initialize()
    await brain_logger.log_event(event_type, message, status, user_id, metadata)


# Sync wrapper for non-async contexts
def log_event_sync(
    event_type: str,
    message: str,
    status: Literal["success", "error", "warning", "info", "pending"] = "info",
    user_id: Optional[int] = None,
    metadata: Optional[dict] = None
):
    """Synchronous logging (console only, no Telegram)."""
    event_icon = EVENT_ICONS.get(event_type, "📌")
    status_icon = STATUS_ICONS.get(status, "ℹ️")

    log_level = logging.ERROR if status == "error" else logging.WARNING if status == "warning" else logging.INFO
    console_msg = f"[{event_type.upper()}] {status_icon} {message}"
    if user_id:
        console_msg += f" (user: {user_id})"
    logger.log(log_level, console_msg)
