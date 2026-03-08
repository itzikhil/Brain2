import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import Optional

from app.models.orm import User, ConversationState

logger = logging.getLogger(__name__)


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
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            return {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "created_at": user.created_at
            }

        # Create new user
        new_user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
        self.db.add(new_user)
        await self.db.flush()
        await self.db.refresh(new_user)

        return {
            "id": new_user.id,
            "telegram_id": new_user.telegram_id,
            "username": new_user.username,
            "first_name": new_user.first_name,
            "created_at": new_user.created_at
        }

    async def get_conversation_state(self, user_id: int) -> dict:
        """Get user's conversation state."""
        stmt = select(ConversationState).where(ConversationState.user_id == user_id)
        result = await self.db.execute(stmt)
        state = result.scalar_one_or_none()

        if state:
            return {"current_state": state.current_state, "context": state.context}

        return {"current_state": "idle", "context": {}}

    async def set_conversation_state(
        self,
        user_id: int,
        state: str,
        context: dict = None
    ) -> None:
        """Set user's conversation state."""
        # Use PostgreSQL upsert (INSERT ... ON CONFLICT)
        stmt = pg_insert(ConversationState).values(
            user_id=user_id,
            current_state=state,
            context=context or {}
        ).on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "current_state": state,
                "context": context or {}
            }
        )

        await self.db.execute(stmt)
