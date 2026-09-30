import logging
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
    scheduler = AsyncIOScheduler()
except ImportError:
    AsyncIOScheduler = None
    CronTrigger = None
    HAS_APSCHEDULER = False
    scheduler = None

def parse_time_to_cron(time_str: str):
    """Parse '08:30' into (hour=8, minute=30)."""
    try:
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 8, 30

async def job_daily_radar():
    """
    Scheduled job: runs source collection, trend detection, and daily idea generation.
    """
    logger.info("[Scheduler] Triggering daily radar pipeline run...")
    try:
        from app.orchestrator.pipeline import run_pipeline
        result = await run_pipeline(send_telegram=True)
        logger.info(f"[Scheduler] Daily radar finished: {result.get('message')}")
    except Exception as e:
        logger.error(f"[Scheduler] Error running scheduled radar: {e}", exc_info=True)

async def job_posting_reminder():
    """
    Scheduled job: sends posting reminder via Telegram if there are saved ideas.
    """
    logger.info("[Scheduler] Triggering posting reminder...")
    try:
        from app.models.database import SessionLocal
        from app.models.models import ContentIdea
        from app.services.telegram import telegram_service

        db = SessionLocal()
        saved_count = db.query(ContentIdea).filter(ContentIdea.status == "saved").count()
        db.close()

        if saved_count > 0:
            await telegram_service.send_posting_reminder(saved_count=saved_count)
    except Exception as e:
        logger.error(f"[Scheduler] Error sending posting reminder: {e}")

def init_scheduler():
    if not HAS_APSCHEDULER or not scheduler:
        logger.warning("[Scheduler] apscheduler is not installed in the active environment. Background cron jobs skipped.")
        return

    if not settings.ENABLE_SCHEDULER:
        logger.info("[Scheduler] Disabled via settings.")
        return

    # Add daily radar job
    d_hour, d_min = parse_time_to_cron(settings.DAILY_DIGEST_TIME)
    scheduler.add_job(
        job_daily_radar,
        CronTrigger(hour=d_hour, minute=d_min),
        id="daily_radar_job",
        replace_existing=True
    )
    logger.info(f"[Scheduler] Scheduled Daily Radar at {d_hour:02d}:{d_min:02d}")

    # Add posting reminder job
    r_hour, r_min = parse_time_to_cron(settings.POSTING_REMINDER_TIME)
    scheduler.add_job(
        job_posting_reminder,
        CronTrigger(hour=r_hour, minute=r_min),
        id="posting_reminder_job",
        replace_existing=True
    )
    logger.info(f"[Scheduler] Scheduled Posting Reminder at {r_hour:02d}:{r_min:02d}")

    scheduler.start()
    logger.info("[Scheduler] Started successfully.")

def shutdown_scheduler():
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("[Scheduler] Shut down.")
