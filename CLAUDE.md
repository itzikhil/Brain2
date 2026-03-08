# External Brain

Personal knowledge management system with OCR, vector search, and Telegram integration.

## Stack
- **Framework**: FastAPI (Railway deployment)
- **Database**: PostgreSQL + pgvector
- **Bot**: python-telegram-bot
- **AI**: Google Gemini 1.5 Flash (OCR/translation), text-embedding-004 (vectors)

## Core Features
1. **Document Filing**: Photo → OCR → Translate German → Vector embed → Store
2. **Shopping List**: Stateful sessions with add/check/clear/close
3. **Associative Retrieval**: Natural language search across all knowledge

## Quick Start
```bash
cp .env.example .env  # Add credentials
pip install -r requirements.txt
psql -f init.sql  # Initialize DB
uvicorn app.main:app --reload
```

## Key Commands
- `/add <item>` - Add to shopping list
- `/list` - Show shopping list
- `/remember <text>` - Store memory
- `/search <query>` - Search everything
- Send photo - OCR German document

## Skills
See `.claude/skills/` for detailed logic documentation.
