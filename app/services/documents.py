import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import Optional
from uuid import UUID

from app.models.orm import Document, User
from app.services.gemini import GeminiService
from app.services.logger import log_event

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.gemini = GeminiService()

    async def process_document(
        self,
        user_id: int,
        image_bytes: bytes,
        filename: Optional[str] = None
    ) -> dict:
        """Process document: OCR, translate, embed, and store."""
        await log_event(
            "document",
            f"Processing document: {filename or 'unnamed'}",
            "pending",
            user_id=user_id,
            metadata={"size_bytes": len(image_bytes)}
        )

        # OCR and translate
        try:
            ocr_result = await self.gemini.ocr_and_translate(image_bytes)
            await log_event(
                "ocr",
                f"OCR completed: {ocr_result['document_type']}",
                "success",
                user_id=user_id,
                metadata={"chars_extracted": len(ocr_result['original_text'])}
            )
        except Exception as e:
            await log_event(
                "ocr",
                f"Gemini OCR failed: {str(e)[:100]}",
                "error",
                user_id=user_id,
                metadata={"filename": filename}
            )
            raise

        # Generate embedding from combined text
        try:
            combined_text = f"{ocr_result['original_text']}\n\n{ocr_result['translated_text']}"
            embedding = await self.gemini.generate_embedding(combined_text)
            await log_event(
                "embedding",
                f"Vector created: {len(embedding)}d",
                "success",
                user_id=user_id
            )
        except Exception as e:
            await log_event(
                "embedding",
                f"Embedding generation failed: {str(e)[:100]}",
                "error",
                user_id=user_id
            )
            raise

        # Store in database using ORM
        try:
            new_doc = Document(
                user_id=user_id,
                filename=filename,
                original_text=ocr_result["original_text"],
                translated_text=ocr_result["translated_text"],
                source_language="de",
                target_language="en",
                embedding=embedding,
                file_type=ocr_result["document_type"],
                doc_metadata={"summary": ocr_result["summary"]}
            )
            self.db.add(new_doc)
            await self.db.flush()
            await self.db.refresh(new_doc)

            doc_id = str(new_doc.id)
            await log_event(
                "document",
                f"Document saved: {doc_id[:8]}...",
                "success",
                user_id=user_id,
                metadata={
                    "doc_type": ocr_result["document_type"],
                    "filename": filename
                }
            )

            return {
                "id": doc_id,
                "original_text": ocr_result["original_text"],
                "translated_text": ocr_result["translated_text"],
                "document_type": ocr_result["document_type"],
                "summary": ocr_result["summary"],
                "created_at": new_doc.created_at
            }
        except Exception as e:
            await log_event(
                "document",
                f"Database insert failed: {str(e)[:100]}",
                "error",
                user_id=user_id
            )
            raise

    async def search_documents(
        self,
        user_id: int,
        query: str,
        limit: int = 5
    ) -> list[dict]:
        """Search documents using vector similarity."""
        await log_event(
            "search",
            f"Document search: '{query[:50]}'",
            "info",
            user_id=user_id
        )

        query_embedding = await self.gemini.generate_query_embedding(query)

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

        await log_event(
            "search",
            f"Found {len(rows)} documents",
            "success",
            user_id=user_id
        )

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
