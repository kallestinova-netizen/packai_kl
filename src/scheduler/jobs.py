import logging
import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from src.config import ADMIN_USER_IDS, DB_PATH, BACKUP_DIR, load_topic_bank, save_topic_bank, load_schedule
from src.modules.perplexity_news import fetch_news_via_perplexity
from src.modules.news_parser import parse_all_feeds
from src.modules.content_generator import generate_post
from src.modules.trend_researcher import discover_emerging_trends, research_trend
from src.db.queries import (
    get_todays_news,
    get_todays_plan_post,
    get_yesterday_stats,
    save_generated_content,
    save_news,
    log_activity,
)
from src.bot.callbacks import get_news_keyboard, get_format_keyboard, get_trend_keyboard

logger = logging.getLogger(__name__)


async def job_news_parse(bot: Bot):
    """07:00 — Fetch news via Perplexity API, fallback to RSS."""
    logger.info("Running scheduled news parse")
    try:
        # Try Perplexity first
        results = await fetch_news_via_perplexity()

        if results:
            logger.info(f"Perplexity returned {len(results)} news items")
            for item in results:
                await save_news(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=item.get("source", "Perplexity"),
                    summary=item.get("summary", ""),
                    score=item.get("score", 50),
                )
            await log_activity("scheduled", "news_parse", f"perplexity: {len(results)} items")
        else:
            # Fallback to RSS
            logger.info("Perplexity returned no results, falling back to RSS")
            results = await parse_all_feeds()
            await log_activity("scheduled", "news_parse", f"rss_fallback: {len(results)} items")
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


async def job_trend_discover(bot: Bot):
    """09:00 — Discover emerging trends and deep-research the top one."""
    logger.info("Running trend discovery")
    try:
        trends = await discover_emerging_trends()
        if not trends or len(trends) == 0:
            logger.warning("No emerging trends found")
            return

        # Deep research the first trend
        first = trends[0]
        result = await research_trend(first["topic"])

        if result is None:
            # Research unavailable — notify and schedule retry
            for admin_id in ADMIN_USER_IDS:
                await bot.send_message(
                    admin_id,
                    "Исследование трендов временно недоступно. Попробую через час.",
                )
            await log_activity("scheduled", "trend_discover", "research_failed, retry_in_1h")
            _schedule_trend_retry(bot, first, trends)
            return

        await _send_trend_result(bot, first, result, trends)
        await log_activity("scheduled", "trend_discover", f"topic={first['topic']}")

    except Exception as e:
        logger.error(f"Trend discovery failed: {e}")


async def _job_trend_retry(bot: Bot, first: dict, trends: list):
    """Retry trend research after 1 hour."""
    logger.info(f"Retrying trend research: {first['topic']}")
    try:
        result = await research_trend(first["topic"])
        if result is None:
            for admin_id in ADMIN_USER_IDS:
                await bot.send_message(
                    admin_id,
                    "Повторная попытка исследования трендов не удалась. Попробуйте вручную: /trend " + first["topic"],
                )
            return
        await _send_trend_result(bot, first, result, trends)
        await log_activity("scheduled", "trend_discover_retry", f"topic={first['topic']}")
    except Exception as e:
        logger.error(f"Trend retry failed: {e}")


def _schedule_trend_retry(bot: Bot, first: dict, trends: list):
    """Schedule a one-time retry in 1 hour."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.date import DateTrigger
        from datetime import timedelta

        # Get the running scheduler from the bot's data or create trigger
        run_at = datetime.now() + timedelta(hours=1)
        # Use the existing scheduler if available
        scheduler = getattr(bot, "_scheduler", None)
        if scheduler and isinstance(scheduler, AsyncIOScheduler):
            scheduler.add_job(
                _job_trend_retry,
                DateTrigger(run_date=run_at),
                args=[bot, first, trends],
                id="trend_retry",
                replace_existing=True,
            )
            logger.info(f"Scheduled trend retry at {run_at}")
        else:
            logger.warning("Scheduler not available for trend retry")
    except Exception as e:
        logger.error(f"Failed to schedule trend retry: {e}")


async def _send_trend_result(bot: Bot, first: dict, result: dict, trends: list):
    """Format and send trend research results to admins."""
    # Stats line
    stats = (
        f"Reddit {result.get('reddit_count', 0)} тредов "
        f"({result.get('reddit_upvotes', 0)} апвоутов) | "
        f"X {result.get('x_count', 0)} постов "
        f"({result.get('x_likes', 0)} лайков) | "
        f"YouTube {result.get('youtube_count', 0)} видео"
    )

    # Key insights
    insights = result.get("key_insights", [])
    insights_text = "\n".join(f"  -> {ins}" for ins in insights) if insights else "  -> Нет данных"

    # Top discussions
    top_reddit = result.get("top_reddit", {})
    top_x = result.get("top_x", {})
    top_youtube = result.get("top_youtube", {})

    top_text = ""
    if top_reddit:
        top_text += f"Reddit: {top_reddit.get('title', '—')} ({top_reddit.get('upvotes', 0)} апвоутов)\n"
    if top_x:
        top_text += f"X: {top_x.get('text', '—')[:100]} ({top_x.get('likes', 0)} лайков)\n"
    if top_youtube:
        top_text += f"YouTube: {top_youtube.get('title', '—')} ({top_youtube.get('views', 0)} просмотров)\n"
    if not top_text:
        top_text = "Нет данных\n"

    # Other trends
    other_trends = ""
    for idx, t in enumerate(trends[1:3], 2):
        other_trends += f"{idx}. {t.get('title_ru', t.get('topic', ''))} — {t.get('why_emerging', '')}\n"

    text = (
        f"ЗАРОЖДАЮЩИЙСЯ ТРЕНД\n\n"
        f"{first.get('title_ru', first.get('topic', ''))}\n"
        f"Сигнал: {first.get('signal', '')}\n"
        f"{first.get('why_emerging', '')}\n\n"
        f"{stats}\n\n"
        f"КЛЮЧЕВЫЕ НАХОДКИ:\n{insights_text}\n\n"
        f"ТОП ОБСУЖДЕНИЯ:\n{top_text}\n"
        f"ИДЕЯ ДЛЯ ПОСТА:\n{result.get('post_idea', '—')}\n\n"
    )

    if other_trends:
        text += f"Ещё 2 зарождающихся тренда:\n{other_trends}"

    # Build keyboard with investigate buttons for trends 2 and 3
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons_row1 = [
        InlineKeyboardButton(text="📝 Создать пост", callback_data="trend:post"),
        InlineKeyboardButton(text="🎬 Скрипт", callback_data="trend:video"),
    ]
    buttons_row2 = []
    for idx, t in enumerate(trends[1:3], 2):
        # Store topic in short form for callback (Telegram 64-byte limit)
        short_topic = t.get("topic", "")[:30]
        buttons_row2.append(
            InlineKeyboardButton(
                text=f"🔍 Исследовать #{idx}",
                callback_data=f"trenddig:{short_topic}",
            )
        )

    rows = [buttons_row1]
    if buttons_row2:
        rows.append(buttons_row2)
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    for admin_id in ADMIN_USER_IDS:
        await bot.send_message(admin_id, text, reply_markup=keyboard)
