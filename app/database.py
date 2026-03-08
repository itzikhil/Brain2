import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lazy initialization to avoid import-time issues
_engine = None
_async_session_maker = None

Base = declarative_base()


def get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url

        # Ensure we're using asyncpg driver
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not db_url.startswith("postgresql+asyncpg://"):
            db_url = f"postgresql+asyncpg://{db_url.split('://', 1)[-1]}"

        # Remove sslmode from URL - asyncpg handles SSL via connect_args
        if "sslmode=" in db_url:
            import re
            db_url = re.sub(r'[?&]sslmode=[^&]*', '', db_url)
            # Clean up any trailing ? or &
            db_url = db_url.rstrip('?&')

        logger.info(f"Creating engine with URL: {db_url[:50]}...")

        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"ssl": "require"}  # asyncpg SSL syntax
        )
    return _engine


def get_session_maker():
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
    return _async_session_maker


async def init_db():
    """Initialize database tables if they don't exist."""
    engine = get_engine()

    async with engine.begin() as conn:
        # Check if tables exist by querying for users table
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'users'
            );
        """))
        tables_exist = result.scalar()

        if not tables_exist:
            logger.info("Tables not found. Running schema creation...")

            # Create pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))

            # Create users table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create documents table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    filename VARCHAR(512),
                    original_text TEXT,
                    translated_text TEXT,
                    source_language VARCHAR(10) DEFAULT 'de',
                    target_language VARCHAR(10) DEFAULT 'en',
                    embedding vector(3072),
                    file_type VARCHAR(50),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create shopping_lists table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shopping_lists (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) DEFAULT 'Shopping List',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP WITH TIME ZONE
                );
            """))

            # Create shopping_items table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shopping_items (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    list_id UUID REFERENCES shopping_lists(id) ON DELETE CASCADE,
                    item_name VARCHAR(255) NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    unit VARCHAR(50),
                    is_checked BOOLEAN DEFAULT FALSE,
                    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create memories table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    category VARCHAR(100),
                    embedding vector(3072),
                    source VARCHAR(50) DEFAULT 'manual',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create conversation_states table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS conversation_states (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                    current_state VARCHAR(50) DEFAULT 'idle',
                    context JSONB DEFAULT '{}',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create indexes
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_shopping_lists_user_active ON shopping_lists(user_id, is_active);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_shopping_items_list_id ON shopping_items(list_id);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(user_id, category);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_states_user_id ON conversation_states(user_id);"))

            logger.info("Database tables created successfully!")
        else:
            logger.info("Database tables already exist.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for services."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
