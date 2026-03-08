-- External Brain Database Schema
-- PostgreSQL + pgvector for associative memory

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table (Telegram users)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);

-- Documents table (OCR'd documents with embeddings)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(512),
    original_text TEXT,
    translated_text TEXT,
    source_language VARCHAR(10) DEFAULT 'de',
    target_language VARCHAR(10) DEFAULT 'en',
    embedding vector(3072),  -- Gemini embedding dimension
    file_type VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Shopping lists table
CREATE TABLE IF NOT EXISTS shopping_lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) DEFAULT 'Shopping List',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_shopping_lists_user_active ON shopping_lists(user_id, is_active);

-- Shopping list items
CREATE TABLE IF NOT EXISTS shopping_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_id UUID REFERENCES shopping_lists(id) ON DELETE CASCADE,
    item_name VARCHAR(255) NOT NULL,
    quantity INTEGER DEFAULT 1,
    unit VARCHAR(50),
    is_checked BOOLEAN DEFAULT FALSE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_shopping_items_list_id ON shopping_items(list_id);

-- Memory entries (general knowledge storage)
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    category VARCHAR(100),
    embedding vector(3072),
    source VARCHAR(50) DEFAULT 'manual',  -- manual, document, conversation
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_memories_user_id ON memories(user_id);
CREATE INDEX idx_memories_category ON memories(user_id, category);
CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Conversation context (for stateful interactions)
CREATE TABLE IF NOT EXISTS conversation_states (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    current_state VARCHAR(50) DEFAULT 'idle',
    context JSONB DEFAULT '{}',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversation_states_user_id ON conversation_states(user_id);

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_states_updated_at
    BEFORE UPDATE ON conversation_states
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Helper function for vector similarity search
CREATE OR REPLACE FUNCTION search_similar_documents(
    query_embedding vector(3072),
    user_id_param INTEGER,
    limit_param INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    original_text TEXT,
    translated_text TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.original_text,
        d.translated_text,
        1 - (d.embedding <=> query_embedding) as similarity
    FROM documents d
    WHERE d.user_id = user_id_param
    ORDER BY d.embedding <=> query_embedding
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- Helper function for memory search
CREATE OR REPLACE FUNCTION search_memories(
    query_embedding vector(3072),
    user_id_param INTEGER,
    limit_param INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    category VARCHAR(100),
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.content,
        m.category,
        1 - (m.embedding <=> query_embedding) as similarity
    FROM memories m
    WHERE m.user_id = user_id_param
    ORDER BY m.embedding <=> query_embedding
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;
