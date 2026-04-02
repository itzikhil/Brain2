"""Entry point for Brain2 bot - supports both polling and webhook modes."""
import logging
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_polling():
    """Run bot in polling mode (for local development)."""
    logger.info("Starting bot in POLLING mode...")

    # Initialize database
    from app.database import init_db
    await init_db()
    logger.info("Database initialized")

    # Create and start bot
    from app.bot import create_bot_application
    application = create_bot_application()

    await application.initialize()
    await application.start()
    logger.info("Bot started - listening for updates via polling...")

    # Run polling
    await application.updater.start_polling(
        allowed_updates=["message", "edited_message", "callback_query"]
    )

    # Keep running until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received stop signal")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped")


def run_webhook():
    """Run bot in webhook mode (for Railway deployment)."""
    logger.info("Starting bot in WEBHOOK mode...")

    import uvicorn
    from app.config import get_settings

    settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info"
    )


def main():
    """Main entry point - choose mode based on BOT_MODE setting."""
    from app.config import get_settings

    settings = get_settings()
    mode = settings.bot_mode.lower()

    logger.info(f"BOT_MODE={mode}")

    if mode == "polling":
        asyncio.run(run_polling())
    elif mode == "webhook":
        run_webhook()
    else:
        logger.error(f"Invalid BOT_MODE: {mode}. Must be 'polling' or 'webhook'")
        raise ValueError(f"Invalid BOT_MODE: {mode}")


if __name__ == "__main__":
    main()
