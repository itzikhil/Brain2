"""
External Brain - FastAPI Application
"""
import logging
import asyncio

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from telegram import Update

from app.config import get_settings
from app.bot import create_bot_application
from app.database import init_db
from app.routers import documents, shopping, memory

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global state
_bot_app = None
_initialized = False
_init_lock = asyncio.Lock()


# Create FastAPI app
app = FastAPI(
    title="External Brain",
    description="Personal knowledge management with OCR, vector search, and Telegram integration",
    version="1.0.0"
)


# =============================================================================
# HEALTH CHECK - Simple, no dependencies on initialization
# =============================================================================
@app.get("/health")
async def health_check():
    """Railway health check."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"name": "External Brain", "version": "1.0.0", "status": "ready"}


@app.get("/status")
async def status():
    """Check initialization status."""
    return {
        "initialized": _initialized,
        "bot_ready": _bot_app is not None
    }


# =============================================================================
# INITIALIZATION - Only runs once
# =============================================================================
async def ensure_initialized():
    """Initialize bot and database once."""
    global _bot_app, _initialized

    if _initialized:
        return _bot_app

    async with _init_lock:
        # Double-check after acquiring lock
        if _initialized:
            return _bot_app

        logger.info("=== INITIALIZING ===")

        try:
            # Initialize database
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database ready")

            # Verify Gemini
            settings = get_settings()
            if settings.gemini_api_key and not settings.gemini_api_key.startswith("["):
                logger.info(f"GEMINI_API_KEY: {settings.gemini_api_key[:10]}...")

            # Initialize bot
            logger.info("Creating bot...")
            _bot_app = create_bot_application()
            await _bot_app.initialize()
            await _bot_app.start()
            logger.info("Bot ready")

            _initialized = True
            logger.info("=== INITIALIZATION COMPLETE ===")

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    return _bot_app


# =============================================================================
# WEBHOOK ENDPOINTS
# =============================================================================
@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint."""
    settings = get_settings()

    # Validate secret token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.telegram_webhook_secret:
        logger.warning("Invalid webhook secret")
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    try:
        # Ensure initialized
        bot_app = await ensure_initialized()
        if not bot_app:
            return JSONResponse(status_code=503, content={"error": "Bot not ready"})

        # Process update
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
        settings = get_settings()
        bot_app = await ensure_initialized()

        if not bot_app:
            return JSONResponse(status_code=503, content={"error": "Bot not ready"})

        await bot_app.bot.set_webhook(
            url=f"{webhook_url}/webhook/telegram",
            secret_token=settings.telegram_webhook_secret
        )
        return {"status": "success", "webhook_url": f"{webhook_url}/webhook/telegram"}

    except Exception as e:
        logger.error(f"Set webhook error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# API ROUTERS
# =============================================================================
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(shopping.router, prefix="/api/shopping", tags=["Shopping"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])

logger.info("External Brain app created")
