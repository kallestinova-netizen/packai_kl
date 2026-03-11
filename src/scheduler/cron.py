import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from aiogram import Bot

from src.config import load_schedule
from src.scheduler.jobs import (
    job_news_parse,
    job_morning_digest,
    job_howto_post,
    job_personal_post,
    job_publish_reminder,
    job_evening_summary,
    job_daily_backup,
    job_trend_discover,
)

logger = logging.getLogger(__name__)

DAY_MAP = {
    "mon": "mon",
    "tue": "tue",
    "wed": "wed",
    "thu": "thu",
    "fri": "fri",
    "sat": "sat",
    "sun": "sun",
}


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    schedule = load_schedule()
    tz = schedule.get("timezone", "Asia/Novosibirsk")
    jobs = schedule.get("jobs", {})

    scheduler = AsyncIOScheduler(timezone=tz)

    # News parse — daily
    if "news_parse" in jobs:
        h, m = jobs["news_parse"].split(":")
        scheduler.add_job(
            job_news_parse, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="news_parse", replace_existing=True,
        )
        logger.info(f"Scheduled news_parse at {jobs['news_parse']} {tz}")

    # Morning digest — daily
    if "morning_digest" in jobs:
        h, m = jobs["morning_digest"].split(":")
        scheduler.add_job(
            job_morning_digest, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="morning_digest", replace_existing=True,
        )
        logger.info(f"Scheduled morning_digest at {jobs['morning_digest']} {tz}")

    # How-To posts — specific days
    if "howto_post" in jobs:
        howto = jobs["howto_post"]
        days = ",".join(howto["days"])
        h, m = howto["time"].split(":")
        scheduler.add_job(
            job_howto_post, CronTrigger(day_of_week=days, hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="howto_post", replace_existing=True,
        )
        logger.info(f"Scheduled howto_post on {days} at {howto['time']} {tz}")

    # Personal Brand posts — specific days
    if "personal_post" in jobs:
        personal = jobs["personal_post"]
        days = ",".join(personal["days"])
        h, m = personal["time"].split(":")
        scheduler.add_job(
            job_personal_post, CronTrigger(day_of_week=days, hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="personal_post", replace_existing=True,
        )
        logger.info(f"Scheduled personal_post on {days} at {personal['time']} {tz}")

    # Publish reminder — daily
    if "publish_reminder" in jobs:
        h, m = jobs["publish_reminder"].split(":")
        scheduler.add_job(
            job_publish_reminder, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="publish_reminder", replace_existing=True,
        )
        logger.info(f"Scheduled publish_reminder at {jobs['publish_reminder']} {tz}")

    # Evening summary — daily
    if "evening_summary" in jobs:
        h, m = jobs["evening_summary"].split(":")
        scheduler.add_job(
            job_evening_summary, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="evening_summary", replace_existing=True,
        )
        logger.info(f"Scheduled evening_summary at {jobs['evening_summary']} {tz}")

    # Daily backup — daily
    if "daily_backup" in jobs:
        h, m = jobs["daily_backup"].split(":")
        scheduler.add_job(
            job_daily_backup, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="daily_backup", replace_existing=True,
        )
        logger.info(f"Scheduled daily_backup at {jobs['daily_backup']} {tz}")

    # Trend discover — daily
    if "trend_discover" in jobs:
        h, m = jobs["trend_discover"].split(":")
        scheduler.add_job(
            job_trend_discover, CronTrigger(hour=int(h), minute=int(m), timezone=tz),
            args=[bot], id="trend_discover", replace_existing=True,
        )
        logger.info(f"Scheduled trend_discover at {jobs['trend_discover']} {tz}")

    # Store scheduler reference on bot for retry scheduling
    bot._scheduler = scheduler

    return scheduler
