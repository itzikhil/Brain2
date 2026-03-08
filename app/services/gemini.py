import google.generativeai as genai
from typing import Optional
import base64
import numpy as np

from app.config import get_settings


class GeminiService:
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.vision_model = genai.GenerativeModel("gemini-2.0-flash")
        self.embedding_model = "models/gemini-embedding-001"

    async def ocr_and_translate(
        self,
        image_bytes: bytes,
        source_lang: str = "German",
        target_lang: str = "English"
    ) -> dict:
        """Extract text from image and translate it."""
        image_data = base64.b64encode(image_bytes).decode("utf-8")

        prompt = f"""Analyze this image and perform the following:
1. Extract ALL text visible in the image (OCR)
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

        response = await self.vision_model.generate_content_async([
            {"mime_type": "image/jpeg", "data": image_data},
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
        result = genai.embed_content(
            model=self.embedding_model,
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]

    async def generate_query_embedding(self, text: str) -> list[float]:
        """Generate embedding for search query."""
        result = genai.embed_content(
            model=self.embedding_model,
            content=text,
            task_type="retrieval_query"
        )
        return result["embedding"]

    async def answer_with_context(
        self,
        query: str,
        context_docs: list[dict]
    ) -> str:
        """Generate answer using retrieved context."""
        context_text = "\n\n---\n\n".join([
            f"Document {i+1} (similarity: {doc.get('similarity', 'N/A'):.2f}):\n{doc.get('content', '')}"
            for i, doc in enumerate(context_docs)
        ])

        prompt = f"""Based on the following documents from the user's personal knowledge base, answer their question.
If the documents don't contain relevant information, say so.

RETRIEVED DOCUMENTS:
{context_text}

USER QUESTION: {query}

ANSWER:"""

        response = await self.vision_model.generate_content_async(prompt)
        return response.text
