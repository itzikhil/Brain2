from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


# User schemas
class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None


class User(UserCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Document schemas
class DocumentCreate(BaseModel):
    filename: Optional[str] = None
    original_text: str
    translated_text: Optional[str] = None
    source_language: str = "de"
    target_language: str = "en"
    file_type: Optional[str] = None
    metadata: dict = {}


class Document(BaseModel):
    id: UUID
    user_id: int
    filename: Optional[str]
    original_text: str
    translated_text: Optional[str]
    source_language: str
    target_language: str
    file_type: Optional[str]
    metadata: dict
    created_at: datetime

    class Config:
        from_attributes = True


# Shopping list schemas
class ShoppingItemCreate(BaseModel):
    item_name: str
    quantity: int = 1
    unit: Optional[str] = None


class ShoppingItem(ShoppingItemCreate):
    id: UUID
    list_id: UUID
    is_checked: bool = False
    added_at: datetime

    class Config:
        from_attributes = True


class ShoppingListCreate(BaseModel):
    name: str = "Shopping List"


class ShoppingList(BaseModel):
    id: UUID
    user_id: int
    name: str
    is_active: bool
    items: List[ShoppingItem] = []
    created_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Memory schemas
class MemoryCreate(BaseModel):
    content: str
    category: Optional[str] = None
    source: str = "manual"
    metadata: dict = {}


class Memory(MemoryCreate):
    id: UUID
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Search schemas
class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    search_documents: bool = True
    search_memories: bool = True


class SearchResult(BaseModel):
    id: UUID
    content: str
    source_type: str  # 'document' or 'memory'
    similarity: float
    metadata: dict = {}


# Conversation state
class ConversationState(BaseModel):
    user_id: int
    current_state: str = "idle"
    context: dict = {}
