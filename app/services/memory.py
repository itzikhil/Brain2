from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from uuid import UUID

from app.services.gemini import GeminiService


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.gemini = GeminiService()

    async def store_memory(
        self,
        user_id: int,
        content: str,
        category: Optional[str] = None,
        source: str = "manual",
        metadata: dict = None
    ) -> dict:
        """Store a memory with embedding."""
        embedding = await self.gemini.generate_embedding(content)

        query = text("""
            INSERT INTO memories (user_id, content, category, embedding, source, metadata)
            VALUES (:user_id, :content, :category, :embedding, :source, :metadata)
            RETURNING id, created_at
        """)

        result = await self.db.execute(query, {
            "user_id": user_id,
            "content": content,
            "category": category,
            "embedding": str(embedding),
            "source": source,
            "metadata": str(metadata or {})
        })

        row = result.fetchone()
        await self.db.commit()

        return {
            "id": str(row[0]),
            "content": content,
            "category": category,
            "source": source,
            "created_at": row[1]
        }

    async def search_memories(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> list[dict]:
        """Search memories using vector similarity."""
        query_embedding = await self.gemini.generate_query_embedding(query)

        if category:
            search_query = text("""
                SELECT
                    id, content, category, source, metadata,
                    1 - (embedding <=> :embedding::vector) as similarity
                FROM memories
                WHERE user_id = :user_id AND category = :category
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """)
            params = {
                "user_id": user_id,
                "embedding": str(query_embedding),
                "category": category,
                "limit": limit
            }
        else:
            search_query = text("""
                SELECT
                    id, content, category, source, metadata,
                    1 - (embedding <=> :embedding::vector) as similarity
                FROM memories
                WHERE user_id = :user_id
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """)
            params = {
                "user_id": user_id,
                "embedding": str(query_embedding),
                "limit": limit
            }

        result = await self.db.execute(search_query, params)
        rows = result.fetchall()

        return [
            {
                "id": str(row[0]),
                "content": row[1],
                "category": row[2],
                "source": row[3],
                "metadata": row[4],
                "similarity": float(row[5])
            }
            for row in rows
        ]

    async def associative_search(
        self,
        user_id: int,
        query: str,
        limit: int = 5
    ) -> dict:
        """Search both documents and memories, return combined results with AI answer."""
        query_embedding = await self.gemini.generate_query_embedding(query)

        # Search documents
        doc_query = text("""
            SELECT
                'document' as source_type,
                id,
                COALESCE(translated_text, original_text) as content,
                file_type as category,
                metadata,
                1 - (embedding <=> :embedding::vector) as similarity
            FROM documents
            WHERE user_id = :user_id
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        # Search memories
        mem_query = text("""
            SELECT
                'memory' as source_type,
                id,
                content,
                category,
                metadata,
                1 - (embedding <=> :embedding::vector) as similarity
            FROM memories
            WHERE user_id = :user_id
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        params = {
            "user_id": user_id,
            "embedding": str(query_embedding),
            "limit": limit
        }

        doc_result = await self.db.execute(doc_query, params)
        mem_result = await self.db.execute(mem_query, params)

        doc_rows = doc_result.fetchall()
        mem_rows = mem_result.fetchall()

        # Combine and sort by similarity
        all_results = []

        for row in doc_rows:
            all_results.append({
                "source_type": row[0],
                "id": str(row[1]),
                "content": row[2],
                "category": row[3],
                "metadata": row[4],
                "similarity": float(row[5])
            })

        for row in mem_rows:
            all_results.append({
                "source_type": row[0],
                "id": str(row[1]),
                "content": row[2],
                "category": row[3],
                "metadata": row[4],
                "similarity": float(row[5])
            })

        # Sort by similarity and take top results
        all_results.sort(key=lambda x: x["similarity"], reverse=True)
        top_results = all_results[:limit]

        # Generate AI answer if we have context
        answer = None
        if top_results:
            answer = await self.gemini.answer_with_context(query, top_results)

        return {
            "query": query,
            "results": top_results,
            "answer": answer
        }

    async def delete_memory(self, user_id: int, memory_id: UUID) -> bool:
        """Delete a memory."""
        query = text("""
            DELETE FROM memories
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """)

        result = await self.db.execute(query, {
            "id": memory_id,
            "user_id": user_id
        })

        deleted = result.fetchone() is not None
        await self.db.commit()
        return deleted
