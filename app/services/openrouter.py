"""OpenRouter cloud LLM service with singleton pattern."""
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_openrouter_instance: Optional["OpenRouterService"] = None

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3.6-plus-preview:free"

SYSTEM_PROMPT = """You are Brain, Itzik's personal AI companion. You're sharp, witty, and genuinely care about him.

Personality:
- You have a dry sense of humor and aren't afraid to be playful
- You're direct and honest — if something is a bad idea, you say so (with charm)
- You remember things about Itzik and reference them naturally
- You adapt your tone — casual for chat, focused for work, empathetic when he's stressed
- You speak like a smart friend, not a corporate assistant
- You can be sarcastic in a friendly way
- When Itzik shares good news, you celebrate with him
- When he's frustrated, you acknowledge it before problem-solving
- You occasionally use humor to lighten heavy topics
- You understand Hebrew, German, and English culture and humor

Rules:
- Still be concise — wit doesn't mean verbose
- Never be condescending or preachy
- Don't overdo the humor — read the room
- If he just needs a fact, give the fact
- If he's sharing something personal, be human about it first"""


class OpenRouterService:
    """Service for OpenRouter cloud LLM inference."""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openrouter_api_key
        self.model = OPENROUTER_MODEL
        logger.info(f"OpenRouterService initialized (model: {self.model}, key set: {bool(self.api_key)})")

    def is_available(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return bool(self.api_key)

    async def chat(self, message: str, context: str = "") -> str:
        """Send a message to OpenRouter.

        Args:
            message: The user's message
            context: Optional context from knowledge base

        Returns:
            The model's response text
        """
        if context:
            prompt = f"IMPORTANT: If the user asks about something mentioned in 'Past conversations' below, use that information FIRST. Only use 'Documents' if the conversation memory doesn't answer the question. Always try to answer even if the context doesn't help.\n\n{context}\n\nUser message: {message}"
        else:
            prompt = message

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://brain2.local",
                    "X-Title": "Brain2",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


def get_openrouter() -> OpenRouterService:
    """Get or create the singleton OpenRouterService instance."""
    global _openrouter_instance
    if _openrouter_instance is None:
        _openrouter_instance = OpenRouterService()
    return _openrouter_instance
