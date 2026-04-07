"""Ollama local LLM service with singleton pattern."""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_ollama_instance: Optional["OllamaService"] = None

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:26b"


class OllamaService:
    """Service for local Ollama LLM inference."""

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        logger.info(f"OllamaService initialized (model: {self.model})")

    async def is_available(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    DEFAULT_SYSTEM_PROMPT = """You are Brain, Itzik's personal AI companion. You're sharp, witty, and genuinely care about him.

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
- If he's sharing something personal, be human about it first
- Keep responses under 3 sentences for simple questions. Be warm but efficient."""

    async def chat(self, message: str, context: str = "", model: str | None = None, system_prompt: str | None = None) -> str:
        """Send a message to the local Ollama model.

        Args:
            message: The user's message
            context: Optional context from knowledge base
            model: Optional model override (uses default if None)
            system_prompt: Optional system prompt override

        Returns:
            The model's response text
        """
        if context:
            prompt = f"""You may use the following context if relevant, but always try to answer the user's question even if the context doesn't help:

Context: {context}

User message: {message}"""
        else:
            prompt = message

        system = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        use_model = model or self.model

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": use_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]


def get_ollama() -> OllamaService:
    """Get or create the singleton OllamaService instance."""
    global _ollama_instance
    if _ollama_instance is None:
        _ollama_instance = OllamaService()
    return _ollama_instance
