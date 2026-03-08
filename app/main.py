"""
External Brain - FastAPI Application
Health check is defined FIRST with zero dependencies.
"""
import logging

# Configure logging FIRST
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import ONLY FastAPI - nothing else at top level
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# Create app immediately
app = FastAPI(
    title="External Brain",
    description="Personal knowledge management with OCR, vector search, and Telegram integration",
    version="1.0.0"
)


# =============================================================================
# HEALTH CHECK - MUST BE FIRST, ZERO DEPENDENCIES
# =============================================================================
@app.get("/health")
async def health_check():
    """Railway health check - returns immediately, no dependencies."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"name": "External Brain", "version": "1.0.0", "status": "ready"}


# =============================================================================
# LAZY INITIALIZATION - All imports inside functions
# =============================================================================
_bot_app = None
_initialized = False
_init_error = None


async def ensure_initialized():
    """Lazy initialization - all imports happen here, not at module load."""
    global _bot_app, _initialized, _init_error

    if _initialized:
        return _bot_app

    if _init_error:
        raise _init_error

    import asyncio
    lock = asyncio.Lock()

    async with lock:
        if _initialized:
            return _bot_app

        logger.info("=== LAZY INITIALIZATION STARTING ===")

        try:
            # Import config
            logger.info("Loading config...")
            from app.config import get_settings
            settings = get_settings()
            logger.info("Config loaded")

            # Import and init database
            logger.info("Initializing database...")
            from app.database import init_db
            await init_db()
            logger.info("Database initialized")

            # Verify Gemini
            if not settings.gemini_api_key or settings.gemini_api_key.startswith("["):
                logger.warning("GEMINI_API_KEY may be invalid")
            else:
                logger.info(f"GEMINI_API_KEY: {settings.gemini_api_key[:10]}...")

            # Import and init bot
            logger.info("Creating bot application...")
            from app.bot import create_bot_application
            _bot_app = create_bot_application()
            await _bot_app.initialize()
            await _bot_app.start()
            logger.info("Bot started")

            _initialized = True
            logger.info("=== INITIALIZATION COMPLETE ===")

        except Exception as e:
            logger.error(f"=== INITIALIZATION FAILED: {e} ===")
            import traceback
            traceback.print_exc()
            _init_error = e
            raise

    return _bot_app


# =============================================================================
# WEBHOOK ENDPOINTS
# =============================================================================
@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram webhook - triggers lazy init on first request."""
    try:
        # Import config here to avoid top-level import issues
        from app.config import get_settings
        settings = get_settings()

        # Validate token first
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_token != settings.telegram_webhook_secret:
            logger.warning("Invalid webhook secret token")
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        # Lazy init
        bot_app = await ensure_initialized()
        if not bot_app:
            return JSONResponse(status_code=503, content={"error": "Bot not ready"})

        # Process update
        from telegram import Update
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
        from app.config import get_settings
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


@app.get("/status")
async def status():
    """Check initialization status."""
    return {
        "initialized": _initialized,
        "bot_ready": _bot_app is not None,
        "error": str(_init_error) if _init_error else None
    }


# =============================================================================
# ROUTERS - Wrapped in try/except to prevent crash
# =============================================================================
try:
    from app.routers import documents, shopping, memory
    app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
    app.include_router(shopping.router, prefix="/api/shopping", tags=["Shopping"])
    app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
    logger.info("API routers loaded")
except Exception as e:
    logger.error(f"Failed to load routers: {e}")
    # App continues without API routes - health check still works
