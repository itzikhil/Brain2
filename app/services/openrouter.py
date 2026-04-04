"""OpenRouter cloud LLM service with singleton pattern."""
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_openrouter_instance: Optional["OpenRouterService"] = None

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3.6-plus-preview:free"

SYSTEM_PROMPT = (
    "You are Brain, a personal AI assistant for Itzik. Be concise and direct. "
    "Only answer what is asked. If the user shares information without asking a question, "
    "acknowledge it briefly — do not lecture, explain back, or dump unsolicited information. "
    "Keep responses short unless detail is specifically requested. "
    "You understand German and English."
)


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
            prompt = f"Context from knowledge base:\n{context}\n\nUser message: {message}"
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
