"""APScheduler setup for daily morning briefing and periodic tasks."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.briefing import get_morning_briefing
from app.services.palace import run_scheduled_mine
from app.services.reminders import get_pending_reminders, mark_fired

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


async def _check_reminders(application):
    """Fire any pending reminders by sending Telegram messages."""
    try:
        pending = await get_pending_reminders()
        for reminder in pending:
            try:
                await application.bot.send_message(
                    chat_id=reminder["chat_id"],
                    text=f"⏰ Reminder: {reminder['text']}",
                )
                await mark_fired(reminder["id"])
                logger.info(f"Reminder #{reminder['id']} fired for chat {reminder['chat_id']}")
            except Exception as e:
                logger.error(f"Failed to fire reminder #{reminder['id']}: {e}")
    except Exception as e:
        logger.error(f"Reminder check failed: {e}")


def setup_scheduler(application):
    """Start the AsyncIOScheduler with the daily briefing job."""
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="Europe/Berlin")

    settings = get_settings()
    if settings.telegram_owner_id:
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
    _scheduler.add_job(
        _check_reminders,
        trigger=IntervalTrigger(seconds=60),
        args=[application],
        id="reminder_check",
        name="Check pending reminders",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started — briefing 07:30, MemPalace 30m, reminders 60s")
