"""Gemini AI service with singleton pattern."""
import logging
import google.generativeai as genai
from typing import Optional
import base64

from app.config import get_settings

logger = logging.getLogger(__name__)

_gemini_instance: Optional["GeminiService"] = None


class GeminiService:
    """Singleton service for Google Gemini AI."""

    SYSTEM_PROMPT = "You are Brain, a personal assistant. The user is based in Germany."

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

        # Use the specified model for chat/OCR
        self.chat_model = genai.GenerativeModel(
            "gemini-2.5-flash-preview-05-20",
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

    async def chat(self, message: str, context: Optional[str] = None) -> str:
        """
        Send a message to Gemini and get a response.

        Args:
            message: The user's message
            context: Optional context from knowledge base to include

        Returns:
            The AI's response
        """
        if context:
            prompt = f"""Context from knowledge base:
{context}

User message: {message}"""
        else:
            prompt = message

        response = await self.chat_model.generate_content_async(prompt)
        return response.text

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
2. The document is in {source_lang}
3. Translate the extracted text to {target_lang}
4. Identify the document type (letter, invoice, form, receipt, etc.)

Respond in this exact format:
ORIGINAL_TEXT:
[extracted text in original language]

TRANSLATED_TEXT:
[translated text]

DOCUMENT_TYPE:
[type of document]

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
            "translated_text": "",
            "document_type": "",
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
            elif line_stripped.startswith("SUMMARY:"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "summary"
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

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
