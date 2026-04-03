"""Document processing service with OCR, translation, and vector storage."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from app.models.orm import Document
from app.services.gemini import get_gemini
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def _map_language_to_code(language: str) -> str:
    """Map language name to ISO 639-1 code."""
    language_map = {
        "german": "de",
        "deutsch": "de",
        "english": "en",
        "eng": "en",
        "spanish": "es",
        "español": "es",
        "french": "fr",
        "français": "fr",
        "italian": "it",
        "italiano": "it",
        "portuguese": "pt",
        "português": "pt",
        "dutch": "nl",
        "nederlands": "nl",
        "polish": "pl",
        "polski": "pl",
        "russian": "ru",
        "русский": "ru",
        "chinese": "zh",
        "中文": "zh",
        "japanese": "ja",
        "日本語": "ja",
        "korean": "ko",
        "한국어": "ko",
        "arabic": "ar",
        "العربية": "ar",
        "turkish": "tr",
        "türkçe": "tr",
    }

    # Try to match language name (case-insensitive)
    lang_lower = language.lower().strip()
    if lang_lower in language_map:
        return language_map[lang_lower]

    # If already a 2-letter code, return as-is (truncated to 10 chars for safety)
    if len(language) == 2:
        return language.lower()

    # Otherwise, return the original (truncated to 10 chars)
    return language[:10].lower()


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_document(
        self,
        user_id: int,
        image_bytes: bytes,
        filename: Optional[str] = None
    ) -> dict:
        """Process document: OCR, translate, embed, and store."""
        logger.info(f"Processing document: {filename or 'unnamed'} ({len(image_bytes)} bytes)")

        gemini = get_gemini()

        # OCR and translate
        try:
            ocr_result = await gemini.ocr_and_translate(image_bytes)
            logger.info(f"OCR completed: {ocr_result['document_type']} ({len(ocr_result['original_text'])} chars)")
        except Exception as e:
            logger.error(f"Gemini OCR failed: {e}")
            raise

        # Generate embedding from combined text
        try:
            combined_text = f"{ocr_result['original_text']}\n\n{ocr_result['translated_text']}"
            embedding = await gemini.generate_embedding(combined_text)
            logger.info(f"Embedding generated: {len(embedding)}d")
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

        # Upload original file to R2 storage
        storage = get_storage()
        r2_key = None
        if storage.enabled:
            logger.info(f"R2 storage enabled - uploading document: {filename or 'unnamed'}")
            r2_key = storage.upload_document(
                file_bytes=image_bytes,
                filename=filename or "document",
                document_type=ocr_result["document_type"],
                category="documents"
            )
            if r2_key:
                logger.info(f"Document uploaded to R2 successfully - key: {r2_key}")
            else:
                logger.warning(f"R2 upload returned None for {filename or 'unnamed'}")
        else:
            logger.info("R2 storage not enabled - skipping file upload")

        # Store in database using ORM
        try:
            metadata = {"summary": ocr_result["summary"]}
            if r2_key:
                metadata["r2_key"] = r2_key

            # Add amount and sender to metadata if present
            if ocr_result.get("amount") and ocr_result["amount"].lower() != "none":
                metadata["amount"] = ocr_result["amount"]
            if ocr_result.get("sender") and ocr_result["sender"].lower() != "none":
                metadata["sender"] = ocr_result["sender"]

            # Map detected language to language code
            detected_language = ocr_result.get("language", "")
            source_lang = _map_language_to_code(detected_language)

            # Only set target_language if translation was actually done
            is_english = source_lang == "en"
            target_lang = None if is_english else "en"

            new_doc = Document(
                user_id=user_id,
                filename=filename,
                original_text=ocr_result["original_text"],
                translated_text=ocr_result["translated_text"],
                source_language=source_lang,
                target_language=target_lang,
                embedding=embedding,
                file_type=ocr_result["document_type"],
                doc_metadata=metadata
            )
            self.db.add(new_doc)
            await self.db.flush()
            await self.db.refresh(new_doc)

            doc_id = str(new_doc.id)
            logger.info(f"Document saved: {doc_id[:8]}... ({ocr_result['document_type']})")

            return {
                "id": doc_id,
                "original_text": ocr_result["original_text"],
                "translated_text": ocr_result["translated_text"],
                "document_type": ocr_result["document_type"],
                "language": ocr_result.get("language", ""),
                "amount": ocr_result.get("amount", ""),
                "sender": ocr_result.get("sender", ""),
                "summary": ocr_result["summary"],
                "created_at": new_doc.created_at
            }
        except Exception as e:
            logger.error(f"Database insert failed: {e}")
            raise

    async def search_documents(
        self,
        user_id: int,
        query: str,
        limit: int = 5
    ) -> list[dict]:
        """Search documents using vector similarity."""
        logger.info(f"Document search: '{query[:50]}'")

        gemini = get_gemini()
        query_embedding = await gemini.generate_query_embedding(query)

        # Use SQLAlchemy with pgvector cosine distance
        stmt = (
            select(
                Document.id,
                Document.original_text,
                Document.translated_text,
                Document.file_type,
                Document.doc_metadata,
                (1 - Document.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .where(Document.user_id == user_id)
            .order_by(Document.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        logger.info(f"Found {len(rows)} documents")

        return [
            {
                "id": str(row.id),
                "original_text": row.original_text,
                "translated_text": row.translated_text,
                "document_type": row.file_type,
                "metadata": row.doc_metadata,
                "similarity": float(row.similarity) if row.similarity else 0.0
            }
            for row in rows
        ]

    async def get_document(self, document_id: UUID, user_id: int) -> Optional[dict]:
        """Get a specific document."""
        stmt = (
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )

        result = await self.db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return {
            "id": str(doc.id),
            "original_text": doc.original_text,
            "translated_text": doc.translated_text,
            "document_type": doc.file_type,
            "metadata": doc.doc_metadata,
            "created_at": doc.created_at
        }

    async def get_latest_document(self, user_id: int, limit: int = 1) -> list[dict]:
        """
        Get the most recent document(s) for a user.

        Args:
            user_id: The user ID
            limit: Number of documents to return (default: 1)

        Returns:
            List of documents ordered by created_at DESC
        """
        logger.info(f"Fetching latest {limit} document(s) for user {user_id}")

        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        docs = result.scalars().all()

        logger.info(f"Found {len(docs)} latest document(s)")

        return [
            {
                "id": str(doc.id),
                "original_text": doc.original_text,
                "translated_text": doc.translated_text,
                "document_type": doc.file_type,
                "metadata": doc.doc_metadata,
                "created_at": doc.created_at,
                "filename": doc.filename
            }
            for doc in docs
        ]
