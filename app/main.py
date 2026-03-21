"""External Brain - FastAPI app with lazy initialization."""
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="External Brain")

# Lazy initialization state
_bot = None
_ready = False


@app.get("/health")
async def health():
    """Health check endpoint for Railway."""
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "ready"}


@app.get("/status")
async def status():
    """Check if bot is initialized."""
    return {"ready": _ready}


@app.post("/webhook/telegram")
async def webhook(request: Request):
    """
    Telegram webhook endpoint with lazy initialization.

    Only initializes the bot on first request to speed up deployment.
    """
    global _bot, _ready

    try:
        # Verify webhook secret
        from app.config import get_settings
        settings = get_settings()

        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.telegram_webhook_secret:
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        # Lazy initialization on first request
        if not _ready:
            logger.info("Initializing on first request...")

            from app.database import init_db
            await init_db()
            logger.info("Database ready")

            from app.bot import create_bot_application
            _bot = create_bot_application()
            await _bot.initialize()
            await _bot.start()
            logger.info("Bot ready")

            _ready = True

        # Process update
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot.bot)
        await _bot.process_update(update)
        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/webhook/set")
async def set_webhook(webhook_url: str):
    """Set Telegram webhook URL."""
    global _bot, _ready

    try:
        from app.config import get_settings
        settings = get_settings()

        if not _ready:
            from app.database import init_db
            await init_db()

            from app.bot import create_bot_application
            _bot = create_bot_application()
            await _bot.initialize()
            await _bot.start()
            _ready = True

        await _bot.bot.set_webhook(
            url=f"{webhook_url}/webhook/telegram",
            secret_token=settings.telegram_webhook_secret
        )
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Webhook set error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


logger.info("FastAPI app ready - health check available at /health")
