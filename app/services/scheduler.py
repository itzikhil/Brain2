"""APScheduler setup for daily morning briefing and periodic tasks."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.briefing import get_morning_briefing
from app.services.palace import run_scheduled_mine

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _send_briefing(application):
    """Fetch briefing and send it to the owner via Telegram."""
    settings = get_settings()
    if not settings.telegram_owner_id:
        logger.warning("TELEGRAM_OWNER_ID not set — skipping briefing")
        return

    try:
        text = await get_morning_briefing()
        await application.bot.send_message(
            chat_id=settings.telegram_owner_id,
            text=text,
        )
        logger.info("Morning briefing sent")
    except Exception as e:
        logger.error(f"Failed to send morning briefing: {e}")


def setup_scheduler(application):
    """Start the AsyncIOScheduler with the daily briefing job."""
    global _scheduler

    settings = get_settings()
    if not settings.telegram_owner_id:
        logger.warning("TELEGRAM_OWNER_ID not set — scheduler not started")
        return

    _scheduler = AsyncIOScheduler(timezone="Europe/Berlin")
    _scheduler.add_job(
        _send_briefing,
        trigger=CronTrigger(hour=7, minute=30),
        args=[application],
        id="morning_briefing",
        name="Daily morning briefing",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_scheduled_mine,
        trigger=IntervalTrigger(minutes=30),
        id="mempalace_mine",
        name="MemPalace conversation mining",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started — morning briefing at 07:30, MemPalace mining every 30m")
