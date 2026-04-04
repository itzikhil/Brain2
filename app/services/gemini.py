"""Gemini AI service with singleton pattern and privacy-aware routing."""
import logging
import google.generativeai as genai
from typing import Optional
import base64

from app.config import get_settings
from app.services.privacy import classify_privacy
from app.services.ollama import get_ollama
from app.services.openrouter import get_openrouter

logger = logging.getLogger(__name__)

_gemini_instance: Optional["GeminiService"] = None


class GeminiService:
    """Singleton service for Google Gemini AI."""

    SYSTEM_PROMPT = "You are Brain, a personal AI assistant for Itzik. Be concise and direct. Only answer what is asked. If the user shares information without asking a question, acknowledge it briefly — do not lecture, explain back, or dump unsolicited information. Keep responses short unless detail is specifically requested. You understand German and English."

    def __init__(self):
        settings = get_settings()

        # Validate API key
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set!")
        if api_key.startswith("[") or api_key == "your_gemini_api_key_here":
            raise ValueError(f"GEMINI_API_KEY appears to be a placeholder: {api_key[:20]}...")

        logger.info(f"Initializing Gemini with API key: {api_key[:10]}...")
        genai.configure(api_key=api_key)

        # Use stable model aliases for chat/OCR
        self.chat_model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=self.SYSTEM_PROMPT
        )
        self.embedding_model = "gemini-embedding-001"
        logger.info("GeminiService initialized successfully")

    def _detect_mime_type(self, file_bytes: bytes) -> str:
        """Detect MIME type from file magic bytes."""
        if file_bytes[:4] == b'%PDF':
            return "application/pdf"
        elif file_bytes[:3] == b'\xff\xd8\xff':
            return "image/jpeg"
        elif file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
            return "image/webp"
        elif file_bytes[:3] == b'GIF':
            return "image/gif"
        else:
            return "image/jpeg"  # Default fallback

    async def chat(self, message: str, context: Optional[str] = None) -> tuple[str, str]:
        """
        Send a message to the appropriate model based on privacy classification.

        Args:
            message: The user's message
            context: Optional context from knowledge base to include

        Returns:
            Tuple of (response text, model indicator: "local" or "cloud")
        """
        privacy_level = classify_privacy(message)

        if privacy_level == "S3":
            ollama = get_ollama()
            if await ollama.is_available():
                logger.info("🔒 Using local model (private)")
                response = await ollama.chat(message, context=context or "")
                return response, "local"
            else:
                logger.warning("🔒 Message is private but Ollama unavailable — falling back to Gemini")

        # Try OpenRouter first for S1 messages
        openrouter = get_openrouter()
        if openrouter.is_available():
            try:
                logger.info("☁️ Using OpenRouter (qwen3.6-plus)")
                response = await openrouter.chat(message, context=context or "")
                return response, "cloud"
            except Exception as e:
                logger.warning(f"☁️ OpenRouter failed, falling back to Gemini: {e}")

        logger.info("☁️ Using Gemini (fallback)")

        if context:
            prompt = f"""Context from knowledge base:
{context}

User message: {message}"""
        else:
            prompt = message

        response = await self.chat_model.generate_content_async(prompt)
        return response.text, "cloud"

    async def ocr_and_translate(
        self,
        file_bytes: bytes,
        source_lang: str = "German",
        target_lang: str = "English"
    ) -> dict:
        """Extract text from image/PDF and translate it."""
        file_data = base64.b64encode(file_bytes).decode("utf-8")
        mime_type = self._detect_mime_type(file_bytes)

        prompt = f"""Analyze this document and perform the following:
1. Extract ALL text visible in the document (OCR)
2. Identify the LANGUAGE of the document
3. If the document is NOT in English, translate the extracted text to {target_lang}
4. Identify the document type (letter, invoice, form, receipt, etc.)
5. Extract the AMOUNT (total amount if it's a bill/invoice/receipt, or "none" if not applicable)
6. Extract the SENDER (company or person who sent/issued the document, or "none" if not identifiable)

Respond in this exact format:
ORIGINAL_TEXT:
[extracted text in original language]

LANGUAGE:
[detected language name]

TRANSLATED_TEXT:
[translated text if not English, or same as original if already in English]

DOCUMENT_TYPE:
[type of document]

AMOUNT:
[total amount with currency, or "none"]

SENDER:
[company or person name, or "none"]

SUMMARY:
[brief summary of what this document is about]"""

        response = await self.chat_model.generate_content_async([
            {"mime_type": mime_type, "data": file_data},
            prompt
        ])

        result_text = response.text
        return self._parse_ocr_response(result_text)

    def _parse_ocr_response(self, response: str) -> dict:
        """Parse the structured OCR response."""
        sections = {
            "original_text": "",
            "language": "",
            "translated_text": "",
            "document_type": "",
            "amount": "",
            "sender": "",
            "summary": ""
        }

        current_section = None
        current_content = []

        for line in response.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("ORIGINAL_TEXT:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "original_text"
                current_content = []
            elif line_stripped.startswith("LANGUAGE:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "language"
                current_content = []
            elif line_stripped.startswith("TRANSLATED_TEXT:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "translated_text"
                current_content = []
            elif line_stripped.startswith("DOCUMENT_TYPE:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "document_type"
                current_content = []
            elif line_stripped.startswith("AMOUNT:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "amount"
                current_content = []
            elif line_stripped.startswith("SENDER:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "sender"
                current_content = []
            elif line_stripped.startswith("SUMMARY:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "summary"
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        # Truncate fields to match database constraints
        sections["document_type"] = sections["document_type"][:50] if sections["document_type"] else ""
        sections["language"] = sections["language"][:10] if sections["language"] else ""

        return sections

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        result = await genai.embed_content_async(
            model=self.embedding_model,
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]

    async def generate_query_embedding(self, text: str) -> list[float]:
        """Generate embedding for search query."""
        result = await genai.embed_content_async(
            model=self.embedding_model,
            content=text,
            task_type="retrieval_query"
        )
        return result["embedding"]


def get_gemini() -> GeminiService:
    """Get or create the singleton GeminiService instance."""
    global _gemini_instance
    if _gemini_instance is None:
        _gemini_instance = GeminiService()
    return _gemini_instance
