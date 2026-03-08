# Deployment Skill

## Railway Deployment

### Prerequisites
1. Railway account with PostgreSQL addon
2. Telegram Bot Token (from @BotFather)
3. Google Gemini API Key

### Environment Variables
```
DATABASE_URL=postgresql+asyncpg://...
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_SECRET=your_random_secret_string
GEMINI_API_KEY=your_gemini_key
PORT=8000
```

Generate a secure random secret:
```bash
openssl rand -hex 32
```

### Database Setup
1. Add PostgreSQL addon in Railway
2. Enable pgvector extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Run `init.sql` to create schema

### Webhook Setup
After deployment:
```bash
curl -X POST "https://your-app.railway.app/webhook/set?webhook_url=https://your-app.railway.app"
```

### Health Check
Railway uses `/health` endpoint for health checks.

## Local Development

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment
cp .env.example .env
# Edit .env with your credentials

# Run PostgreSQL with pgvector (Docker)
docker run -d --name pgvector \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Initialize database
psql -h localhost -U postgres -d postgres -f init.sql

# Run application
uvicorn app.main:app --reload
```

### Telegram Polling (Development)
For local development without webhook, modify `app/main.py` to use polling instead of webhook mode.

## Files Structure
```
Brain2/
├── app/
│   ├── main.py          # FastAPI app
│   ├── bot.py           # Telegram bot
│   ├── config.py        # Settings
│   ├── database.py      # DB connection
│   ├── models/          # Pydantic schemas
│   ├── routers/         # API endpoints
│   └── services/        # Business logic
├── .claude/skills/      # Claude Code skills
├── init.sql             # Database schema
├── requirements.txt     # Dependencies
├── railway.toml         # Railway config
└── CLAUDE.md           # Project overview
```
