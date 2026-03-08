import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from sqlalchemy.sql import func
from typing import Optional
from uuid import UUID

from app.models.orm import ShoppingList, ShoppingItem

logger = logging.getLogger(__name__)


class ShoppingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_active_list(self, user_id: int) -> dict:
        """Get active shopping list or create one."""
        stmt = (
            select(ShoppingList)
            .where(ShoppingList.user_id == user_id, ShoppingList.is_active == True)
            .order_by(ShoppingList.created_at.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        shopping_list = result.scalar_one_or_none()

        if shopping_list:
            return {
                "id": str(shopping_list.id),
                "name": shopping_list.name,
                "created_at": shopping_list.created_at
            }

        # Create new list
        new_list = ShoppingList(
            user_id=user_id,
            name="Shopping List",
            is_active=True
        )
        self.db.add(new_list)
        await self.db.flush()
        await self.db.refresh(new_list)

        return {
            "id": str(new_list.id),
            "name": new_list.name,
            "created_at": new_list.created_at
        }

    async def add_item(
        self,
        user_id: int,
        item_name: str,
        quantity: int = 1,
        unit: Optional[str] = None
    ) -> dict:
        """Add item to active shopping list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        new_item = ShoppingItem(
            list_id=UUID(shopping_list["id"]),
            item_name=item_name,
            quantity=quantity,
            unit=unit
        )
        self.db.add(new_item)
        await self.db.flush()
        await self.db.refresh(new_item)

        return {
            "id": str(new_item.id),
            "item_name": new_item.item_name,
            "quantity": new_item.quantity,
            "unit": new_item.unit,
            "is_checked": new_item.is_checked,
            "added_at": new_item.added_at,
            "list_id": shopping_list["id"]
        }

    async def list_items(self, user_id: int) -> dict:
        """Get all items from active shopping list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        stmt = (
            select(ShoppingItem)
            .where(ShoppingItem.list_id == UUID(shopping_list["id"]))
            .order_by(ShoppingItem.is_checked, ShoppingItem.added_at)
        )

        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        items = [
            {
                "id": str(item.id),
                "item_name": item.item_name,
                "quantity": item.quantity,
                "unit": item.unit,
                "is_checked": item.is_checked,
                "added_at": item.added_at
            }
            for item in rows
        ]

        return {
            "list": shopping_list,
            "items": items,
            "total_items": len(items),
            "checked_items": sum(1 for item in items if item["is_checked"])
        }

    async def check_item(self, user_id: int, item_id: UUID) -> Optional[dict]:
        """Mark item as checked."""
        # Verify ownership by joining with shopping_lists
        verify_stmt = (
            select(ShoppingItem)
            .join(ShoppingList, ShoppingItem.list_id == ShoppingList.id)
            .where(ShoppingItem.id == item_id, ShoppingList.user_id == user_id)
        )

        result = await self.db.execute(verify_stmt)
        item = result.scalar_one_or_none()

        if not item:
            return None

        # Update the item
        item.is_checked = True
        await self.db.flush()

        return {
            "id": str(item.id),
            "item_name": item.item_name,
            "is_checked": item.is_checked
        }

    async def remove_item(self, user_id: int, item_id: UUID) -> bool:
        """Remove item from list."""
        # First verify ownership
        verify_stmt = (
            select(ShoppingItem.id)
            .join(ShoppingList, ShoppingItem.list_id == ShoppingList.id)
            .where(ShoppingItem.id == item_id, ShoppingList.user_id == user_id)
        )

        result = await self.db.execute(verify_stmt)
        if not result.scalar_one_or_none():
            return False

        # Delete the item
        delete_stmt = delete(ShoppingItem).where(ShoppingItem.id == item_id)
        await self.db.execute(delete_stmt)

        return True

    async def close_list(self, user_id: int) -> Optional[dict]:
        """Close current shopping list session."""
        # Find active list
        stmt = (
            select(ShoppingList)
            .where(ShoppingList.user_id == user_id, ShoppingList.is_active == True)
        )

        result = await self.db.execute(stmt)
        shopping_list = result.scalar_one_or_none()

        if not shopping_list:
            return None

        # Update to close it
        shopping_list.is_active = False
        shopping_list.closed_at = func.current_timestamp()
        await self.db.flush()
        await self.db.refresh(shopping_list)

        return {
            "id": str(shopping_list.id),
            "name": shopping_list.name,
            "created_at": shopping_list.created_at,
            "closed_at": shopping_list.closed_at
        }

    async def clear_checked(self, user_id: int) -> int:
        """Remove all checked items from active list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        # Delete checked items
        delete_stmt = (
            delete(ShoppingItem)
            .where(
                ShoppingItem.list_id == UUID(shopping_list["id"]),
                ShoppingItem.is_checked == True
            )
            .returning(ShoppingItem.id)
        )

        result = await self.db.execute(delete_stmt)
        deleted_count = len(result.all())

        return deleted_count
