from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.services.documents import DocumentService

router = APIRouter()


@router.post("/upload")
async def upload_document(
    user_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process a document image."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await file.read()
    doc_service = DocumentService(db)

    result = await doc_service.process_document(
        user_id=user_id,
        image_bytes=contents,
        filename=file.filename
    )

    return result


@router.get("/search")
async def search_documents(
    user_id: int,
    query: str,
    limit: int = 5,
    db: AsyncSession = Depends(get_db)
):
    """Search documents using natural language."""
    doc_service = DocumentService(db)
    results = await doc_service.search_documents(
        user_id=user_id,
        query=query,
        limit=limit
    )
    return {"query": query, "results": results}


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document by ID."""
    doc_service = DocumentService(db)
    document = await doc_service.get_document(document_id, user_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document
