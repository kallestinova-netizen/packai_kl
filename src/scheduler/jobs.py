import logging
import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from src.config import ADMIN_USER_IDS, DB_PATH, BACKUP_DIR, load_topic_bank, save_topic_bank
from src.modules.news_parser import parse_all_feeds
from src.modules.content_generator import generate_post
from src.db.queries import (
    get_todays_news,
    get_todays_plan_post,
    get_yesterday_stats,
    save_generated_content,
    log_activity,
)
from src.bot.callbacks import get_news_keyboard, get_format_keyboard

logger = logging.getLogger(__name__)


async def job_news_parse(bot: Bot):
    """07:00 — Parse RSS feeds."""
    logger.info("Running scheduled news parse")
    try:
        results = await parse_all_feeds()
        await log_activity("scheduled", "news_parse", f"found {len(results)} items")
    except Exception as e:
        logger.error(f"News parse failed: {e}")


async def job_morning_digest(bot: Bot):
    """08:00 — Send morning digest to admin."""
    logger.info("Running morning digest")
    try:
        for admin_id in ADMIN_USER_IDS:
            await _send_morning_digest(bot, admin_id)
        await log_activity("scheduled", "morning_digest")
    except Exception as e:
        logger.error(f"Morning digest failed: {e}")


async def _send_morning_digest(bot: Bot, chat_id: int):
    await bot.send_message(chat_id, "☀️ Доброе утро!\n\n📰 Собираю сводку...")

    news = await get_todays_news(limit=3)
    if news:
        for i, item in enumerate(news, 1):
            keyboard = get_news_keyboard(item["id"])
            await bot.send_message(
                chat_id,
                f"📰 {i}. {item['title']}\n\n{item['summary']}\n\n🔗 {item['source']}",
                reply_markup=keyboard,
            )
    else:
        await bot.send_message(chat_id, "📰 Новостей по вашим темам сегодня не найдено.")

    plan_post = await get_todays_plan_post()
    if plan_post:
        content_id = await save_generated_content(
            source_type="plan",
            source_id=plan_post["id"],
            rubric=plan_post["rubric"] or "personal",
            format_name="linkedin",
            text=plan_post["full_text"],
        )
        keyboard = get_format_keyboard(content_id)
        await bot.send_message(
            chat_id,
            f"📋 ПОСТ ДНЯ:\n\n{plan_post['full_text']}",
            reply_markup=keyboard,
        )

    yesterday = await get_yesterday_stats()
    created = yesterday["created"] if yesterday else 0
    approved = yesterday["approved"] if yesterday else 0
    await bot.send_message(chat_id, f"📊 Вчера: {created} создано, {approved} одобрено")


async def job_howto_post(bot: Bot):
    """Tue, Thu, Sat 15:00 — Generate How-To post."""
    logger.info("Running How-To post generation")
    try:
        topic_bank = load_topic_bank()
        topic = None
        topic_idx = None

        for i, t in enumerate(topic_bank.get("howto", [])):
            if not t.get("used", False):
                topic = t
                topic_idx = i
                break

        if not topic:
            logger.info("No unused How-To topics")
            return

        post_text = await generate_post(
            topic=topic["title"],
            format_name="linkedin",
            rubric="howto",
        )

        content_id = await save_generated_content(
            source_type="scheduled",
            source_id=0,
            rubric="howto",
            format_name="linkedin",
            text=post_text,
        )

        # Mark topic as used
        topic_bank["howto"][topic_idx]["used"] = True
        save_topic_bank(topic_bank)

        keyboard = get_format_keyboard(content_id)
        for admin_id in ADMIN_USER_IDS:
            await bot.send_message(
                admin_id,
                f"🔧 How-To Lab\n\n{post_text}",
                reply_markup=keyboard,
            )

        await log_activity("scheduled", "howto_post", f"topic={topic['title']}, content_id={content_id}")
    except Exception as e:
        logger.error(f"How-To post generation failed: {e}")


async def job_personal_post(bot: Bot):
    """Mon, Wed, Fri 15:00 — Generate Personal Brand post."""
    logger.info("Running Personal Brand post generation")
    try:
        topic_bank = load_topic_bank()
        topic = None
        topic_idx = None

        for i, t in enumerate(topic_bank.get("personal", [])):
            if not t.get("used", False):
                topic = t
                topic_idx = i
                break

        if not topic:
            logger.info("No unused Personal topics")
            return

        post_text = await generate_post(
            topic=f"{topic['title']} (тип: {topic.get('type', 'reality')})",
            format_name="linkedin",
            rubric="personal",
        )

        content_id = await save_generated_content(
            source_type="scheduled",
            source_id=0,
            rubric="personal",
            format_name="linkedin",
            text=post_text,
        )

        topic_bank["personal"][topic_idx]["used"] = True
        save_topic_bank(topic_bank)

        keyboard = get_format_keyboard(content_id)
        for admin_id in ADMIN_USER_IDS:
            await bot.send_message(
                admin_id,
                f"👤 Personal Brand\n\n{post_text}",
                reply_markup=keyboard,
            )

        await log_activity("scheduled", "personal_post", f"topic={topic['title']}, content_id={content_id}")
    except Exception as e:
        logger.error(f"Personal post generation failed: {e}")


async def job_publish_reminder(bot: Bot):
    """12:00 — Reminder to publish approved posts."""
    logger.info("Running publish reminder")
    try:
        for admin_id in ADMIN_USER_IDS:
            await bot.send_message(
                admin_id,
                "🔔 Напоминание: проверь одобренные посты и опубликуй!\n\n"
                "Используй /plan чтобы увидеть статус контент-плана.",
            )
        await log_activity("scheduled", "publish_reminder")
    except Exception as e:
        logger.error(f"Publish reminder failed: {e}")


async def job_evening_summary(bot: Bot):
    """20:00 — Evening summary."""
    logger.info("Running evening summary")
    try:
        yesterday = await get_yesterday_stats()
        created = yesterday["created"] if yesterday else 0
        approved = yesterday["approved"] if yesterday else 0

        for admin_id in ADMIN_USER_IDS:
            await bot.send_message(
                admin_id,
                f"🌙 Итоги дня:\n\n"
                f"📝 Создано постов: {created}\n"
                f"✅ Одобрено: {approved}\n\n"
                f"Хорошего вечера! 💫",
            )
        await log_activity("scheduled", "evening_summary")
    except Exception as e:
        logger.error(f"Evening summary failed: {e}")


async def job_daily_backup(bot: Bot):
    """03:00 — Backup database."""
    logger.info("Running daily backup")
    try:
        backup_dir = Path(BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"bot_backup_{timestamp}.db"

        shutil.copy2(DB_PATH, backup_path)

        # Keep only last 7 backups
        backups = sorted(backup_dir.glob("bot_backup_*.db"), reverse=True)
        for old_backup in backups[7:]:
            old_backup.unlink()

        await log_activity("scheduled", "daily_backup", f"path={backup_path}")
        logger.info(f"Backup created: {backup_path}")
    except Exception as e:
        logger.error(f"Daily backup failed: {e}")
