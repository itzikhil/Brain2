from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from uuid import UUID


class ShoppingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_active_list(self, user_id: int) -> dict:
        """Get active shopping list or create one."""
        query = text("""
            SELECT id, name, created_at
            FROM shopping_lists
            WHERE user_id = :user_id AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """)

        result = await self.db.execute(query, {"user_id": user_id})
        row = result.first()

        if row:
            return {"id": str(row[0]), "name": row[1], "created_at": row[2]}

        # Create new list
        create_query = text("""
            INSERT INTO shopping_lists (user_id, name, is_active)
            VALUES (:user_id, 'Shopping List', TRUE)
            RETURNING id, name, created_at
        """)

        result = await self.db.execute(create_query, {"user_id": user_id})
        row = result.first()
        await self.db.commit()

        return {"id": str(row[0]), "name": row[1], "created_at": row[2]}

    async def add_item(
        self,
        user_id: int,
        item_name: str,
        quantity: int = 1,
        unit: Optional[str] = None
    ) -> dict:
        """Add item to active shopping list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        query = text("""
            INSERT INTO shopping_items (list_id, item_name, quantity, unit)
            VALUES (:list_id, :item_name, :quantity, :unit)
            RETURNING id, item_name, quantity, unit, is_checked, added_at
        """)

        result = await self.db.execute(query, {
            "list_id": shopping_list["id"],
            "item_name": item_name,
            "quantity": quantity,
            "unit": unit
        })

        row = result.first()
        await self.db.commit()

        return {
            "id": str(row[0]),
            "item_name": row[1],
            "quantity": row[2],
            "unit": row[3],
            "is_checked": row[4],
            "added_at": row[5],
            "list_id": shopping_list["id"]
        }

    async def list_items(self, user_id: int) -> dict:
        """Get all items from active shopping list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        query = text("""
            SELECT id, item_name, quantity, unit, is_checked, added_at
            FROM shopping_items
            WHERE list_id = :list_id
            ORDER BY is_checked, added_at
        """)

        result = await self.db.execute(query, {"list_id": shopping_list["id"]})
        rows = result.all()

        items = [
            {
                "id": str(row[0]),
                "item_name": row[1],
                "quantity": row[2],
                "unit": row[3],
                "is_checked": row[4],
                "added_at": row[5]
            }
            for row in rows
        ]

        return {
            "list": shopping_list,
            "items": items,
            "total_items": len(items),
            "checked_items": sum(1 for item in items if item["is_checked"])
        }

    async def check_item(self, user_id: int, item_id: UUID) -> Optional[dict]:
        """Mark item as checked."""
        # Verify ownership
        verify_query = text("""
            SELECT si.id, si.item_name
            FROM shopping_items si
            JOIN shopping_lists sl ON si.list_id = sl.id
            WHERE si.id = :item_id AND sl.user_id = :user_id
        """)

        result = await self.db.execute(verify_query, {
            "item_id": item_id,
            "user_id": user_id
        })

        if not result.first():
            return None

        update_query = text("""
            UPDATE shopping_items
            SET is_checked = TRUE
            WHERE id = :item_id
            RETURNING id, item_name, is_checked
        """)

        result = await self.db.execute(update_query, {"item_id": item_id})
        row = result.first()
        await self.db.commit()

        return {"id": str(row[0]), "item_name": row[1], "is_checked": row[2]}

    async def remove_item(self, user_id: int, item_id: UUID) -> bool:
        """Remove item from list."""
        query = text("""
            DELETE FROM shopping_items si
            USING shopping_lists sl
            WHERE si.list_id = sl.id
                AND si.id = :item_id
                AND sl.user_id = :user_id
            RETURNING si.id
        """)

        result = await self.db.execute(query, {
            "item_id": item_id,
            "user_id": user_id
        })

        deleted = result.first() is not None
        await self.db.commit()
        return deleted

    async def close_list(self, user_id: int) -> Optional[dict]:
        """Close current shopping list session."""
        query = text("""
            UPDATE shopping_lists
            SET is_active = FALSE, closed_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND is_active = TRUE
            RETURNING id, name, created_at, closed_at
        """)

        result = await self.db.execute(query, {"user_id": user_id})
        row = result.first()
        await self.db.commit()

        if not row:
            return None

        return {
            "id": str(row[0]),
            "name": row[1],
            "created_at": row[2],
            "closed_at": row[3]
        }

    async def clear_checked(self, user_id: int) -> int:
        """Remove all checked items from active list."""
        shopping_list = await self.get_or_create_active_list(user_id)

        query = text("""
            DELETE FROM shopping_items
            WHERE list_id = :list_id AND is_checked = TRUE
            RETURNING id
        """)

        result = await self.db.execute(query, {"list_id": shopping_list["id"]})
        deleted_count = len(result.all())
        await self.db.commit()

        return deleted_count
