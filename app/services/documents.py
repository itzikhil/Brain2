from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from uuid import UUID

from app.services.gemini import GeminiService
from app.services.logger import log_event


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

        # Store in database
        try:
            query = text("""
                INSERT INTO documents (
                    user_id, filename, original_text, translated_text,
                    source_language, target_language, embedding, file_type, metadata
                ) VALUES (
                    :user_id, :filename, :original_text, :translated_text,
                    'de', 'en', :embedding, :file_type, :metadata
                )
                RETURNING id, created_at
            """)

            result = await self.db.execute(query, {
                "user_id": user_id,
                "filename": filename,
                "original_text": ocr_result["original_text"],
                "translated_text": ocr_result["translated_text"],
                "embedding": str(embedding),
                "file_type": ocr_result["document_type"],
                "metadata": f'{{"summary": "{ocr_result["summary"]}"}}'
            })

            row = result.fetchone()
            await self.db.commit()

            doc_id = str(row[0])
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
                "created_at": row[1]
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

        search_query = text("""
            SELECT
                id,
                original_text,
                translated_text,
                file_type,
                metadata,
                1 - (embedding <=> :embedding::vector) as similarity
            FROM documents
            WHERE user_id = :user_id
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = await self.db.execute(search_query, {
            "user_id": user_id,
            "embedding": str(query_embedding),
            "limit": limit
        })

        rows = result.fetchall()

        await log_event(
            "search",
            f"Found {len(rows)} documents",
            "success",
            user_id=user_id
        )

        return [
            {
                "id": str(row[0]),
                "original_text": row[1],
                "translated_text": row[2],
                "document_type": row[3],
                "metadata": row[4],
                "similarity": float(row[5])
            }
            for row in rows
        ]

    async def get_document(self, document_id: UUID, user_id: int) -> Optional[dict]:
        """Get a specific document."""
        query = text("""
            SELECT id, original_text, translated_text, file_type, metadata, created_at
            FROM documents
            WHERE id = :id AND user_id = :user_id
        """)

        result = await self.db.execute(query, {"id": document_id, "user_id": user_id})
        row = result.fetchone()

        if not row:
            return None

        return {
            "id": str(row[0]),
            "original_text": row[1],
            "translated_text": row[2],
            "document_type": row[3],
            "metadata": row[4],
            "created_at": row[5]
        }
