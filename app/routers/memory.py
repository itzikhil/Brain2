from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.services.memory import MemoryService
from app.models.schemas import MemoryCreate

router = APIRouter()


@router.post("/store")
async def store_memory(
    user_id: int,
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """Store a new memory."""
    memory_service = MemoryService(db)
    return await memory_service.store_memory(
        user_id=user_id,
        content=memory.content,
        category=memory.category,
        source=memory.source,
        metadata=memory.metadata
    )


@router.get("/search")
async def search_memories(
    user_id: int,
    query: str,
    limit: int = 5,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Search memories using natural language."""
    memory_service = MemoryService(db)
    results = await memory_service.search_memories(
        user_id=user_id,
        query=query,
        limit=limit,
        category=category
    )
    return {"query": query, "results": results}


@router.get("/ask")
async def associative_search(
    user_id: int,
    query: str,
    limit: int = 5,
    db: AsyncSession = Depends(get_db)
):
    """Search all knowledge (documents + memories) and get AI-generated answer."""
    memory_service = MemoryService(db)
    return await memory_service.associative_search(
        user_id=user_id,
        query=query,
        limit=limit
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a memory."""
    memory_service = MemoryService(db)
    deleted = await memory_service.delete_memory(user_id, memory_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"deleted": True}
