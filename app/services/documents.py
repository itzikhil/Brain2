from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from uuid import UUID

from app.services.gemini import GeminiService


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
        # OCR and translate
        ocr_result = await self.gemini.ocr_and_translate(image_bytes)

        # Generate embedding from combined text
        combined_text = f"{ocr_result['original_text']}\n\n{ocr_result['translated_text']}"
        embedding = await self.gemini.generate_embedding(combined_text)

        # Store in database
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

        return {
            "id": str(row[0]),
            "original_text": ocr_result["original_text"],
            "translated_text": ocr_result["translated_text"],
            "document_type": ocr_result["document_type"],
            "summary": ocr_result["summary"],
            "created_at": row[1]
        }

    async def search_documents(
        self,
        user_id: int,
        query: str,
        limit: int = 5
    ) -> list[dict]:
        """Search documents using vector similarity."""
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
