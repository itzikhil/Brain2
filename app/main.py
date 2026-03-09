"""External Brain - Minimal startup to pass health checks."""
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ONLY import FastAPI - nothing else
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="External Brain", version="1.0.0")

# Health check FIRST - zero dependencies
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "ready"}

# Lazy globals
_bot = None
_ready = False

@app.post("/webhook/telegram")
async def webhook(request: Request):
    global _bot, _ready

    try:
        # Lazy import everything
        if not _ready:
            logger.info("First request - initializing...")

            from app.config import get_settings
            settings = get_settings()

            # Validate token
            secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if secret != settings.telegram_webhook_secret:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})

            # Init database
            from app.database import init_db
            await init_db()
            logger.info("Database ready")

            # Init bot
            from app.bot import create_bot_application
            _bot = create_bot_application()
            await _bot.initialize()
            await _bot.start()
            logger.info("Bot ready")

            _ready = True
        else:
            # Already initialized - just validate token
            from app.config import get_settings
            settings = get_settings()
            secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if secret != settings.telegram_webhook_secret:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})

        # Process the update
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot.bot)
        await _bot.process_update(update)
        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/webhook/set")
async def set_webhook(webhook_url: str):
    global _bot, _ready

    try:
        if not _ready:
            from app.database import init_db
            await init_db()

            from app.bot import create_bot_application
            _bot = create_bot_application()
            await _bot.initialize()
            await _bot.start()
            _ready = True

        from app.config import get_settings
        settings = get_settings()

        await _bot.bot.set_webhook(
            url=f"{webhook_url}/webhook/telegram",
            secret_token=settings.telegram_webhook_secret
        )
        return {"status": "success", "url": f"{webhook_url}/webhook/telegram"}

    except Exception as e:
        logger.error(f"Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/status")
async def status():
    return {"ready": _ready, "bot": _bot is not None}

# Try to load routers, but don't crash if they fail
try:
    from app.routers import documents, shopping, memory
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(shopping.router, prefix="/api/shopping")
    app.include_router(memory.router, prefix="/api/memory")
    logger.info("Routers loaded")
except Exception as e:
    logger.error(f"Router load failed (non-fatal): {e}")

logger.info("App created - health check available")
