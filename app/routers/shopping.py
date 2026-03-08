from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.services.shopping import ShoppingService
from app.models.schemas import ShoppingItemCreate

router = APIRouter()


@router.get("/list")
async def get_shopping_list(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get current shopping list with all items."""
    shopping_service = ShoppingService(db)
    return await shopping_service.list_items(user_id)


@router.post("/items")
async def add_shopping_item(
    user_id: int,
    item: ShoppingItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add item to shopping list."""
    shopping_service = ShoppingService(db)
    return await shopping_service.add_item(
        user_id=user_id,
        item_name=item.item_name,
        quantity=item.quantity,
        unit=item.unit
    )


@router.patch("/items/{item_id}/check")
async def check_item(
    item_id: UUID,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Mark item as checked."""
    shopping_service = ShoppingService(db)
    result = await shopping_service.check_item(user_id, item_id)

    if not result:
        raise HTTPException(status_code=404, detail="Item not found")

    return result


@router.delete("/items/{item_id}")
async def remove_item(
    item_id: UUID,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove item from shopping list."""
    shopping_service = ShoppingService(db)
    deleted = await shopping_service.remove_item(user_id, item_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"deleted": True}


@router.post("/clear-checked")
async def clear_checked_items(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove all checked items."""
    shopping_service = ShoppingService(db)
    count = await shopping_service.clear_checked(user_id)
    return {"cleared_count": count}


@router.post("/close")
async def close_shopping_session(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Close current shopping session."""
    shopping_service = ShoppingService(db)
    result = await shopping_service.close_list(user_id)

    if not result:
        raise HTTPException(status_code=404, detail="No active shopping session")

    return result
