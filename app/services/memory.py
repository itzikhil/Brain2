import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, literal
from typing import Optional
from uuid import UUID

from app.models.orm import Memory, Document
from app.services.gemini import GeminiService
from app.services.logger import log_event

logger = logging.getLogger(__name__)


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
        await log_event(
            "memory",
            f"Storing memory: '{content[:50]}...'",
            "pending",
            user_id=user_id,
            metadata={"category": category, "source": source}
        )

        try:
            embedding = await self.gemini.generate_embedding(content)
            await log_event(
                "embedding",
                f"Memory vector created: {len(embedding)}d",
                "success",
                user_id=user_id
            )
        except Exception as e:
            await log_event(
                "embedding",
                f"Memory embedding failed: {str(e)[:100]}",
                "error",
                user_id=user_id
            )
            raise

        try:
            new_memory = Memory(
                user_id=user_id,
                content=content,
                category=category,
                embedding=embedding,
                source=source,
                metadata=metadata or {}
            )
            self.db.add(new_memory)
            await self.db.flush()
            await self.db.refresh(new_memory)

            memory_id = str(new_memory.id)
            await log_event(
                "memory",
                f"Memory saved: {memory_id[:8]}...",
                "success",
                user_id=user_id,
                metadata={"category": category}
            )

            return {
                "id": memory_id,
                "content": content,
                "category": category,
                "source": source,
                "created_at": new_memory.created_at
            }
        except Exception as e:
            await log_event(
                "memory",
                f"Memory save failed: {str(e)[:100]}",
                "error",
                user_id=user_id
            )
            raise

    async def search_memories(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> list[dict]:
        """Search memories using vector similarity."""
        await log_event(
            "search",
            f"Memory search: '{query[:50]}'",
            "info",
            user_id=user_id
        )

        query_embedding = await self.gemini.generate_query_embedding(query)

        # Build SQLAlchemy query with pgvector cosine distance
        stmt = (
            select(
                Memory.id,
                Memory.content,
                Memory.category,
                Memory.source,
                Memory.metadata,
                (1 - Memory.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .where(Memory.user_id == user_id)
        )

        if category:
            stmt = stmt.where(Memory.category == category)

        stmt = (
            stmt
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        await log_event(
            "search",
            f"Found {len(rows)} memories",
            "success",
            user_id=user_id
        )

        return [
            {
                "id": str(row.id),
                "content": row.content,
                "category": row.category,
                "source": row.source,
                "metadata": row.metadata,
                "similarity": float(row.similarity) if row.similarity else 0.0
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
        await log_event(
            "search",
            f"Associative search: '{query[:50]}'",
            "info",
            user_id=user_id
        )

        query_embedding = await self.gemini.generate_query_embedding(query)

        # Search documents using SQLAlchemy
        doc_stmt = (
            select(
                literal("document").label("source_type"),
                Document.id,
                Document.translated_text,
                Document.original_text,
                Document.file_type.label("category"),
                Document.metadata,
                (1 - Document.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .where(Document.user_id == user_id)
            .order_by(Document.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )

        # Search memories using SQLAlchemy
        mem_stmt = (
            select(
                literal("memory").label("source_type"),
                Memory.id,
                Memory.content,
                Memory.category,
                Memory.metadata,
                (1 - Memory.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .where(Memory.user_id == user_id)
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )

        doc_result = await self.db.execute(doc_stmt)
        mem_result = await self.db.execute(mem_stmt)

        doc_rows = doc_result.all()
        mem_rows = mem_result.all()

        # Combine and sort by similarity
        all_results = []

        for row in doc_rows:
            content = row.translated_text or row.original_text
            all_results.append({
                "source_type": row.source_type,
                "id": str(row.id),
                "content": content,
                "category": row.category,
                "metadata": row.metadata,
                "similarity": float(row.similarity) if row.similarity else 0.0
            })

        for row in mem_rows:
            all_results.append({
                "source_type": row.source_type,
                "id": str(row.id),
                "content": row.content,
                "category": row.category,
                "metadata": row.metadata,
                "similarity": float(row.similarity) if row.similarity else 0.0
            })

        # Sort by similarity and take top results
        all_results.sort(key=lambda x: x["similarity"], reverse=True)
        top_results = all_results[:limit]

        await log_event(
            "search",
            f"Associative search complete: {len(doc_rows)} docs, {len(mem_rows)} memories",
            "success",
            user_id=user_id,
            metadata={"top_similarity": top_results[0]["similarity"] if top_results else 0}
        )

        # Generate AI answer if we have context
        answer = None
        if top_results:
            try:
                answer = await self.gemini.answer_with_context(query, top_results)
            except Exception as e:
                await log_event(
                    "error",
                    f"AI answer generation failed: {str(e)[:100]}",
                    "error",
                    user_id=user_id
                )

        return {
            "query": query,
            "results": top_results,
            "answer": answer
        }

    async def delete_memory(self, user_id: int, memory_id: UUID) -> bool:
        """Delete a memory."""
        stmt = (
            delete(Memory)
            .where(Memory.id == memory_id, Memory.user_id == user_id)
            .returning(Memory.id)
        )

        result = await self.db.execute(stmt)
        deleted_row = result.first()
        deleted = deleted_row is not None

        if deleted:
            await log_event(
                "memory",
                f"Memory deleted: {str(memory_id)[:8]}...",
                "info",
                user_id=user_id
            )

        return deleted
