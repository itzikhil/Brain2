from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> dict:
        """Get existing user or create new one."""
        # Try to get existing user
        query = text("""
            SELECT id, telegram_id, username, first_name, created_at
            FROM users
            WHERE telegram_id = :telegram_id
        """)

        result = await self.db.execute(query, {"telegram_id": telegram_id})
        row = result.fetchone()

        if row:
            return {
                "id": row[0],
                "telegram_id": row[1],
                "username": row[2],
                "first_name": row[3],
                "created_at": row[4]
            }

        # Create new user
        create_query = text("""
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (:telegram_id, :username, :first_name)
            RETURNING id, telegram_id, username, first_name, created_at
        """)

        result = await self.db.execute(create_query, {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name
        })

        row = result.fetchone()
        await self.db.commit()

        return {
            "id": row[0],
            "telegram_id": row[1],
            "username": row[2],
            "first_name": row[3],
            "created_at": row[4]
        }

    async def get_conversation_state(self, user_id: int) -> dict:
        """Get user's conversation state."""
        query = text("""
            SELECT current_state, context
            FROM conversation_states
            WHERE user_id = :user_id
        """)

        result = await self.db.execute(query, {"user_id": user_id})
        row = result.fetchone()

        if row:
            return {"current_state": row[0], "context": row[1]}

        return {"current_state": "idle", "context": {}}

    async def set_conversation_state(
        self,
        user_id: int,
        state: str,
        context: dict = None
    ) -> None:
        """Set user's conversation state."""
        query = text("""
            INSERT INTO conversation_states (user_id, current_state, context)
            VALUES (:user_id, :state, :context)
            ON CONFLICT (user_id)
            DO UPDATE SET current_state = :state, context = :context
        """)

        await self.db.execute(query, {
            "user_id": user_id,
            "state": state,
            "context": str(context or {})
        })
        await self.db.commit()
