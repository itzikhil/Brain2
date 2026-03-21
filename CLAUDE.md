# External Brain

Personal knowledge management system with conversational AI, OCR, vector search, and Telegram integration.

## Architecture

This is a **conversational AI agent** that:
- Uses natural language instead of explicit commands
- Automatically searches your knowledge base for context
- Stores memories when you say "remember X"
- Processes photos with OCR and translation
- Maintains a shopping list with structured commands

### File Structure
```
app/
├── main.py              # FastAPI app with lazy webhook initialization
├── bot.py               # Telegram bot with conversational handlers
├── config.py            # Settings via pydantic-settings
├── database.py          # AsyncSession + pgvector setup
├── models/
│   └── orm.py           # SQLAlchemy models (User, Document, Memory, Shopping*)
└── services/
    ├── gemini.py        # Singleton GeminiService (OCR, chat, embeddings)
    ├── documents.py     # Document processing with OCR + translation
    ├── memory.py        # Memory storage + associative search
    ├── shopping.py      # Shopping list management
    └── user.py          # User CRUD
```

## Stack

- **Framework**: FastAPI (Railway deployment with webhook mode)
- **Database**: Neon Postgres + pgvector extension
- **Bot**: python-telegram-bot (async, webhook mode)
- **AI Models**:
  - Google Gemini 2.5 Flash (`gemini-2.5-flash-preview-05-20`) for chat/OCR
  - ⚠️ **ISSUE**: Currently using deprecated `text-embedding-004` → Need to migrate to `gemini-embedding-001`

## Key Design Decisions

1. **Singleton Gemini Service**: Use `get_gemini()` factory function (never instantiate `GeminiService` directly)
2. **`doc_metadata` Rename**: SQLAlchemy reserves `metadata`, so we use `doc_metadata` in models
3. **Lazy Webhook Init**: Bot only initializes on first webhook request to speed up Railway deployment
4. **0.35 Similarity Threshold**: Filters garbage results in associative search
5. **Natural Language Interaction**: No `/remember` or `/search` commands—just talk naturally
6. **Shopping Commands**: Structured commands (`/add`, `/list`, `/clear`, `/done`) for shopping list management

## Environment Variables

Required in `.env`:
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host/db

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_SECRET=random_secret_string
LOG_CHANNEL_ID=-1001234567890  # Optional: log channel for debugging

# Gemini
GEMINI_API_KEY=your_gemini_api_key
```

## Deployment (Railway)

1. **Auto-deploy**: Railway auto-deploys on push to main branch
2. **Set webhook** (one-time setup):
   ```bash
   curl -X POST "https://your-app.railway.app/webhook/set?webhook_url=https://your-app.railway.app"
   ```
3. **Health check**: `GET /health` returns `{"status": "ok"}`

## Current Status

✅ **Working**:
- Natural language chat with context retrieval
- Photo upload for OCR (but embedding broken)
- Shopping list commands
- Lazy webhook initialization

⚠️ **Broken**:
- **Embeddings**: `text-embedding-004` is deprecated → Need to switch to `gemini-embedding-001`
- Document/memory storage works but search may return poor results until fixed

## Phase Roadmap

### Phase 1 (Current) - Core Functionality
- [ ] Fix embedding model (`text-embedding-004` → `gemini-embedding-001`)
- [ ] Test chat with context retrieval
- [ ] Test document upload + OCR + translation
- [ ] Verify associative search quality

### Phase 2 - Reminders
- [ ] Add reminder storage (datetime + message)
- [ ] Implement scheduled Telegram message sender
- [ ] Natural language parsing: "remind me tomorrow at 3pm to buy milk"

### Phase 3 - Email Integration
- [ ] Connect email account (IMAP/SMTP)
- [ ] Parse important emails → store as documents
- [ ] Email search via natural language

### Phase 4 - Local LLM Option
- [ ] Add Ollama integration for chat (Mac M1/M3 privacy mode)
- [ ] Keep Gemini API for OCR (local OCR is hard)
- [ ] Toggle via environment variable

## How It Works

### Natural Language Flow
1. User sends: "remember my passport expires on June 15th"
2. Bot detects "remember" pattern → stores as memory with embedding
3. User asks: "when does my passport expire?"
4. Bot searches memories/documents → finds relevant context
5. Gemini generates response with context: "Your passport expires on June 15th."

### Document Processing Flow
1. User sends photo of German document
2. Gemini OCR extracts text (German)
3. Gemini translates to English
4. Combined text → embedding vector
5. Store in `documents` table with pgvector
6. Return summary + original + translation to user

### Shopping List Flow
- `/add 2 kg apples` → Parse quantity/unit/item → Store in `shopping_items`
- `/list` → Show all items with checkmarks
- `/clear` → Remove checked items
- `/done` → Close shopping session (set `closed_at`)

## Key Commands

**Natural Language** (no prefix):
- "remember my doctor's appointment is on March 25th"
- "what did I save about my lease?"
- "translate this" (with photo)

**Shopping Commands**:
- `/add <item>` - Add item to shopping list (e.g., `/add 2 kg apples`)
- `/list` - Show current shopping list
- `/clear` - Remove checked items
- `/done` - Close shopping session

**Bot Commands**:
- `/start` - Introduction message
- `/help` - Show available commands

## Known Issues & Gotchas

### 1. Gemini Model ID Instability
- Google sometimes deprecates models without warning
- If chat/OCR breaks, check `gemini.py` and update model ID
- Current: `gemini-2.5-flash-preview-05-20` (as of March 2026)

### 2. Embedding Model Deprecated
- `text-embedding-004` is deprecated but still works
- Need to migrate to `gemini-embedding-001`
- Affects: `gemini.py` → `generate_embedding()` and `generate_query_embedding()`

### 3. SQLAlchemy `metadata` Reserved Name
- `metadata` is reserved by SQLAlchemy for schema metadata
- Use `doc_metadata` instead for JSON fields in models
- Affects: `Document.doc_metadata`, `Memory.doc_metadata`

### 4. asyncpg SSL Issues (Neon)
- Neon Postgres requires SSL, but asyncpg may fail with default settings
- Workaround: Add `?sslmode=require` to `DATABASE_URL`

### 5. Similarity Threshold Tuning
- Current: 0.35 (filters most garbage)
- Too high: Misses relevant results
- Too low: Returns irrelevant results
- Adjust in `memory.py:173,186` if needed

### 6. Lazy Init Gotcha
- First webhook request takes ~5-10 seconds (DB + bot init)
- Telegram may timeout and retry
- Subsequent requests are fast

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up .env
cp .env.example .env
# Edit .env with your credentials

# Run locally (polling mode for testing)
python -m app.bot  # If you add polling mode

# Or run FastAPI (webhook mode, needs ngrok)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Then set webhook to your ngrok URL
```

## Database Schema

See `init.sql` for full schema. Key tables:
- `users` - Telegram user info
- `documents` - OCR'd documents with embeddings (pgvector)
- `memories` - User memories with embeddings (pgvector)
- `shopping_lists` - Shopping sessions
- `shopping_items` - Items in shopping lists

## Contributing

When making changes:
1. Update this CLAUDE.md if architecture changes
2. Update `.claude/skills/` if you add new skills
3. Test locally before pushing (Railway auto-deploys)
4. Check logs in Railway dashboard or LOG_CHANNEL_ID on Telegram

## Debugging

- **Railway logs**: Dashboard → Deployments → View logs
- **Telegram log channel**: Set `LOG_CHANNEL_ID` in `.env` for real-time error messages
- **Local logs**: `logging.basicConfig(level=logging.INFO)` in `main.py`

## Skills

See `.claude/skills/` for detailed logic documentation on specific features.
