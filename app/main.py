import logging
import asyncio

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from telegram import Update

from app.config import get_settings

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lazy-initialized globals
_bot_app = None
_init_lock = asyncio.Lock()
_initialized = False


async def ensure_initialized():
    """Lazy initialization of bot and database on first request."""
    global _bot_app, _initialized

    if _initialized:
        return _bot_app

    async with _init_lock:
        # Double-check after acquiring lock
        if _initialized:
            return _bot_app

        logger.info("Lazy initialization starting...")

        try:
            # Initialize database tables if needed
            from app.database import init_db
            logger.info("Checking database tables...")
            await init_db()
            logger.info("Database initialized")

            # Verify Gemini API key
            settings = get_settings()
            if not settings.gemini_api_key or settings.gemini_api_key.startswith("["):
                logger.error("GEMINI_API_KEY is not set or invalid!")
            else:
                logger.info(f"GEMINI_API_KEY configured: {settings.gemini_api_key[:10]}...")

            # Initialize bot
            from app.bot import create_bot_application
            _bot_app = create_bot_application()
            await _bot_app.initialize()
            await _bot_app.start()
            logger.info("Bot initialized successfully")

            _initialized = True
            logger.info("Lazy initialization complete")

        except Exception as e:
            logger.error(f"Initialization error: {e}")
            import traceback
            traceback.print_exc()
            # Don't set _initialized = True, so we retry next time
            raise

    return _bot_app


# Create FastAPI app - NO lifespan handler to avoid blocking startup
app = FastAPI(
    title="External Brain",
    description="Personal knowledge management with OCR, vector search, and Telegram integration",
    version="1.0.0"
)


# Health check - completely decoupled, no dependencies
@app.get("/health")
async def health_check():
    """Critical endpoint for Railway to verify the service is live."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "External Brain",
        "version": "1.0.0",
        "status": "ready",
        "endpoints": {"health": "/health", "webhook": "/webhook/telegram"}
    }


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint - triggers lazy initialization."""
    settings = get_settings()

    # Validate secret token first (doesn't need initialization)
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.telegram_webhook_secret:
        logger.warning("Webhook request with invalid or missing secret token")
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    try:
        # Lazy init on first webhook
        bot_app = await ensure_initialized()

        if not bot_app:
            return JSONResponse(status_code=503, content={"error": "Bot initialization failed"})

        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/webhook/set")
async def set_webhook(webhook_url: str):
    """Set Telegram webhook URL."""
    try:
        bot_app = await ensure_initialized()
        settings = get_settings()

        if not bot_app:
            return JSONResponse(status_code=503, content={"error": "Bot not initialized"})

        await bot_app.bot.set_webhook(
            url=f"{webhook_url}/webhook/telegram",
            secret_token=settings.telegram_webhook_secret
        )
        return {"status": "success", "webhook_url": f"{webhook_url}/webhook/telegram"}

    except Exception as e:
        logger.error(f"Set webhook error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/status")
async def status():
    """Check initialization status."""
    return {
        "initialized": _initialized,
        "bot_ready": _bot_app is not None
    }


# Include routers (they handle their own lazy DB connections)
from app.routers import documents, shopping, memory
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(shopping.router, prefix="/api/shopping", tags=["Shopping"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
