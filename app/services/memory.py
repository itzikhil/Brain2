"""Memory storage and associative search service."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, literal
from typing import Optional
from uuid import UUID

from app.models.orm import Memory, Document
from app.services.gemini import get_gemini

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def store_memory(
        self,
        user_id: int,
        content: str,
        category: Optional[str] = None,
        source: str = "manual",
        metadata: dict = None
    ) -> dict:
        """Store a memory with embedding."""
        logger.info(f"Storing memory: '{content[:50]}...' (category: {category}, source: {source})")

        gemini = get_gemini()

        try:
            embedding = await gemini.generate_embedding(content)
            logger.info(f"Memory vector created: {len(embedding)}d")
        except Exception as e:
            logger.error(f"Memory embedding failed: {e}")
            raise

        try:
            new_memory = Memory(
                user_id=user_id,
                content=content,
                category=category,
                embedding=embedding,
                source=source,
                doc_metadata=metadata or {}
            )
            self.db.add(new_memory)
            await self.db.flush()
            await self.db.refresh(new_memory)

            memory_id = str(new_memory.id)
            logger.info(f"Memory saved: {memory_id[:8]}... (category: {category})")

            return {
                "id": memory_id,
                "content": content,
                "category": category,
                "source": source,
                "created_at": new_memory.created_at
            }
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            raise

    async def search_memories(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> list[dict]:
        """Search memories using vector similarity."""
        logger.info(f"Memory search: '{query[:50]}'")

        gemini = get_gemini()
        query_embedding = await gemini.generate_query_embedding(query)

        # Build SQLAlchemy query with pgvector cosine distance
        stmt = (
            select(
                Memory.id,
                Memory.content,
                Memory.category,
                Memory.source,
                Memory.doc_metadata,
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

        logger.info(f"Found {len(rows)} memories")

        return [
            {
                "id": str(row.id),
                "content": row.content,
                "category": row.category,
                "source": row.source,
                "metadata": row.doc_metadata,
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
        """Search both documents and memories, return combined results."""
        logger.info(f"Associative search: '{query[:50]}'")

        gemini = get_gemini()
        query_embedding = await gemini.generate_query_embedding(query)

        # Search documents using SQLAlchemy
        doc_stmt = (
            select(
                literal("document").label("source_type"),
                Document.id,
                Document.translated_text,
                Document.original_text,
                Document.file_type.label("category"),
                Document.doc_metadata,
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
                Memory.doc_metadata,
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
            similarity = float(row.similarity) if row.similarity else 0.0
            # Apply similarity threshold
            if similarity >= 0.35:
                all_results.append({
                    "source_type": row.source_type,
                    "id": str(row.id),
                    "content": content,
                    "category": row.category,
                    "metadata": row.doc_metadata,
                    "similarity": similarity
                })

        for row in mem_rows:
            similarity = float(row.similarity) if row.similarity else 0.0
            # Apply similarity threshold
            if similarity >= 0.35:
                all_results.append({
                    "source_type": row.source_type,
                    "id": str(row.id),
                    "content": row.content,
                    "category": row.category,
                    "metadata": row.doc_metadata,
                    "similarity": similarity
                })

        # Sort by similarity and take top results
        all_results.sort(key=lambda x: x["similarity"], reverse=True)
        top_results = all_results[:limit]

        logger.info(f"Associative search complete: {len([r for r in doc_rows if (float(r.similarity) if r.similarity else 0) >= 0.35])} docs, {len([r for r in mem_rows if (float(r.similarity) if r.similarity else 0) >= 0.35])} memories above threshold")

        return {
            "query": query,
            "results": top_results
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
            logger.info(f"Memory deleted: {str(memory_id)[:8]}...")

        return deleted
