# Document Filing Skill

## Overview
Process German documents via photo, perform OCR, translate to English, and store with vector embeddings for semantic search.

## Flow
1. User sends photo via Telegram or API
2. Image sent to Gemini 1.5 Flash for OCR
3. Extract: original text, translation, document type, summary
4. Generate embedding from combined text
5. Store in PostgreSQL with pgvector

## Key Files
- `app/services/gemini.py` - OCR and translation via Gemini
- `app/services/documents.py` - Document processing and storage
- `app/bot.py:handle_photo` - Telegram photo handler

## Database
```sql
-- Documents table with vector embedding
documents (
    id UUID,
    user_id INTEGER,
    original_text TEXT,
    translated_text TEXT,
    embedding vector(768),
    file_type VARCHAR,
    metadata JSONB
)
```

## API Endpoints
- `POST /api/documents/upload` - Upload document image
- `GET /api/documents/search?query=...` - Search documents
- `GET /api/documents/{id}` - Get specific document

## Telegram Commands
- Send any photo of a German document
- `/search <query>` - Search stored documents

## Implementation Notes
- Embedding dimension: 3072 (Gemini gemini-embedding-001)
- Uses cosine similarity for vector search
- IVFFlat index with 100 lists for performance
