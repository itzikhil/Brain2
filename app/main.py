"""External Brain - Absolute minimum to pass health check."""
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="External Brain")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "ready"}

# ALL other imports happen ONLY when needed
_bot = None
_ready = False

@app.post("/webhook/telegram")
async def webhook(request: Request):
    global _bot, _ready

    try:
        # Lazy import EVERYTHING
        from app.config import get_settings
        settings = get_settings()

        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.telegram_webhook_secret:
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        if not _ready:
            logger.info("Initializing on first request...")

            from app.database import init_db
            await init_db()
            logger.info("DB ready")

            from app.bot import create_bot_application
            _bot = create_bot_application()
            await _bot.initialize()
            await _bot.start()
            logger.info("Bot ready")

            _ready = True

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
        logger.error(f"Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/status")
async def status():
    return {"ready": _ready}

logger.info("App ready - health check available at /health")
