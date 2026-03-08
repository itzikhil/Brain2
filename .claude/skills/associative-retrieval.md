# Associative Retrieval Skill

## Overview
Natural language queries against stored knowledge (documents + memories) using vector similarity search and AI-powered answer generation.

## Key Files
- `app/services/memory.py` - Memory storage and search
- `app/services/gemini.py` - Embeddings and answer generation
- `app/routers/memory.py` - REST API endpoints

## How It Works
1. User submits natural language query
2. Generate query embedding (optimized for retrieval)
3. Search both documents and memories using cosine similarity
4. Combine and rank results
5. Generate contextual answer using Gemini

## Database Schema
```sql
-- Memories table
memories (
    id UUID,
    user_id INTEGER,
    content TEXT,
    category VARCHAR,
    embedding vector(768),
    source VARCHAR,  -- 'manual', 'document', 'conversation'
    metadata JSONB
)
```

## Vector Search Functions
```sql
-- Document similarity search
search_similar_documents(query_embedding, user_id, limit)

-- Memory similarity search
search_memories(query_embedding, user_id, limit)
```

## Telegram Commands
- `/remember <text>` - Store a memory
- `/search <query>` - Search all knowledge
- `/ask <question>` - Get AI-generated answer
- Direct message - Treated as search query

## API Endpoints
- `POST /api/memory/store` - Store new memory
- `GET /api/memory/search` - Search memories only
- `GET /api/memory/ask` - Full associative search with AI answer
- `DELETE /api/memory/{id}` - Delete memory

## Embedding Types
- `retrieval_document` - For storing content
- `retrieval_query` - For search queries
- Using Gemini gemini-embedding-001 (3072 dimensions)

## Answer Generation
Context is formatted with similarity scores, then Gemini generates a focused answer based on retrieved documents.
