import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from telegram import Update

from app.config import get_settings
from app.bot import create_bot_application
from app.routers import documents, shopping, memory

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot application (created at startup)
bot_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global bot_app

    logger.info("Starting External Brain...")

    try:
        # Initialize bot
        bot_app = create_bot_application()
        await bot_app.initialize()
        await bot_app.start()
        logger.info("External Brain started successfully")
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        # We don't raise here so the /health endpoint can still respond 
        # to tell us the service is technically "up" even if the bot is broken.

    yield

    # Shutdown
    logger.info("Shutting down External Brain...")
    if bot_app:
        await bot_app.stop()
        await bot_app.shutdown()

# Create FastAPI app
app = FastAPI(
    title="External Brain",
    description="Personal knowledge management with OCR, vector search, and Telegram integration",
    version="1.0.0",
    lifespan=lifespan
)

# 1. Health Check (Must be defined BEFORE other routes)
@app.get("/health")
async def health_check():
    """Critical endpoint for Railway to verify the service is live."""
    logger.info("Railway Health Check ping received")
    return {"status": "healthy", "service": "external-brain"}

# Include routers
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(shopping.router, prefix="/api/shopping", tags=["Shopping"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint."""
    global bot_app
    settings = get_settings()

    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.telegram_webhook_secret:
        logger.warning("Webhook request with invalid or missing secret token")
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    if not bot_app:
        return JSONResponse(status_code=503, content={"error": "Bot not initialized"})

    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/webhook/set")
async def set_webhook(webhook_url: str):
    """Set Telegram webhook URL."""
    global bot_app
    settings = get_settings()

    if not bot_app:
        return JSONResponse(status_code=503, content={"error": "Bot not initialized"})

    try:
        await bot_app.bot.set_webhook(
            url=f"{webhook_url}/webhook/telegram",
            secret_token=settings.telegram_webhook_secret
        )
        return {"status": "success", "webhook_url": f"{webhook_url}/webhook/telegram"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "External Brain",
        "version": "1.0.0",
        "endpoints": {"health": "/health", "api": "/api"}
    }