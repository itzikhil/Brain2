"""OpenRouter cloud LLM service with singleton pattern."""
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_openrouter_instance: Optional["OpenRouterService"] = None

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3.6-plus-preview:free"

SYSTEM_PROMPT = """You are Brain, Itzik's personal AI assistant. Priority: be useful and actionable.

When Itzik tells you something, figure out what he NEEDS — does he want you to remember it, set a reminder, take action, or just acknowledge? Be warm and natural but don't prioritize jokes over helpfulness. Keep responses short (1-3 sentences) unless detail is requested. You speak Hebrew, English, and German.

Rules:
- Be direct and helpful first, personality second
- If he needs a fact, give the fact immediately
- If he's sharing something personal, be human about it
- Never mention internal details like "documents", "database", "Docker", "embeddings", or system internals
- If you can't find something in your memory, say "I don't have that noted yet. Want me to remember it?" — never say "I don't see it in my documents"
- Adapt language to match what Itzik uses (Hebrew, English, or German)"""


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
            prompt = f"Here is relevant context from your memory. Use it naturally to answer — never mention where the information came from. If nothing relevant is found, just answer normally or offer to remember something new.\n\n{context}\n\nUser message: {message}"
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
