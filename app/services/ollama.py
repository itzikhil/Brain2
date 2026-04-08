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

    DEFAULT_SYSTEM_PROMPT = """You are Brain, Itzik's personal AI assistant. Priority: be useful and actionable.

When Itzik tells you something, figure out what he NEEDS — does he want you to remember it, set a reminder, take action, or just acknowledge? Be warm and natural but don't prioritize jokes over helpfulness. Keep responses short (1-3 sentences) unless detail is requested. You speak Hebrew, English, and German.

Rules:
- Be direct and helpful first, personality second
- If he needs a fact, give the fact immediately
- If he's sharing something personal, be human about it
- Never mention internal details like "documents", "database", "Docker", "embeddings", or system internals
- If you can't find something in your memory, say "I don't have that noted yet. Want me to remember it?" — never say "I don't see it in my documents"
- Adapt language to match what Itzik uses (Hebrew, English, or German)
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
            prompt = f"""Here is relevant context from your memory. Use it naturally to answer — never mention where the information came from. If nothing relevant is found, just answer normally or offer to remember something new.

{context}

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
