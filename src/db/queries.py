import aiosqlite
import os
from pathlib import Path


DB_PATH = os.getenv("DB_PATH", "data/bot.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "schema.sql"
    async with aiosqlite.connect(DB_PATH) as db:
        with open(schema_path) as f:
            await db.executescript(f.read())
        await db.commit()


# --- News ---

async def save_news(title: str, url: str, source: str, summary: str, score: int = 0):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO news (title, url, source, summary, score) VALUES (?, ?, ?, ?, ?)",
            (title, url, source, summary, score),
        )
        await db.commit()
    finally:
        await db.close()


async def get_todays_news(limit: int = 5):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM news WHERE date(created_at) = date('now') ORDER BY score DESC LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def get_news_by_id(news_id: int):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM news WHERE id = ?", (news_id,))
        return await cursor.fetchone()
    finally:
        await db.close()


async def update_news_generated(news_id: int, format_name: str, text: str):
    db = await get_db()
    try:
        col = f"generated_{format_name}"
        await db.execute(f"UPDATE news SET {col} = ? WHERE id = ?", (text, news_id))
        await db.commit()
    finally:
        await db.close()


async def update_news_status(news_id: int, status: str):
    db = await get_db()
    try:
        await db.execute("UPDATE news SET status = ? WHERE id = ?", (status, news_id))
        await db.commit()
    finally:
        await db.close()


# --- Content Plan ---

async def get_todays_plan_post():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM content_plan WHERE scheduled_date = date('now') AND status = 'ready' LIMIT 1"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def get_all_plan_posts():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM content_plan ORDER BY scheduled_date ASC"
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def update_plan_status(plan_id: int, status: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE content_plan SET status = ? WHERE id = ?", (status, plan_id)
        )
        await db.commit()
    finally:
        await db.close()


# --- Generated Content ---

async def save_generated_content(
    source_type: str,
    source_id: int,
    rubric: str,
    format_name: str,
    text: str,
    status: str = "draft",
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO generated_content (source_type, source_id, rubric, format, text, status) VALUES (?, ?, ?, ?, ?, ?)",
            (source_type, source_id, rubric, format_name, text, status),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_content_by_id(content_id: int):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM generated_content WHERE id = ?", (content_id,)
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def update_content_status(content_id: int, status: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE generated_content SET status = ? WHERE id = ?",
            (status, content_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_content_text(content_id: int, text: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE generated_content SET text = ? WHERE id = ?", (text, content_id)
        )
        await db.commit()
    finally:
        await db.close()


# --- Activity Log ---

async def log_activity(action: str, command: str = None, details: str = None):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO activity_log (action, command, details) VALUES (?, ?, ?)",
            (action, command, details),
        )
        await db.commit()
    finally:
        await db.close()


# --- Stats ---

async def get_stats_week():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved, "
            "SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected "
            "FROM generated_content WHERE created_at >= date('now', '-7 days')"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def get_stats_month():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved, "
            "SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected "
            "FROM generated_content WHERE created_at >= date('now', '-30 days')"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def get_stats_by_rubric():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT rubric, COUNT(*) as count FROM generated_content "
            "WHERE created_at >= date('now', '-30 days') GROUP BY rubric"
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def get_stats_by_format():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT format, COUNT(*) as count FROM generated_content "
            "WHERE created_at >= date('now', '-30 days') GROUP BY format"
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def get_yesterday_stats():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as created, "
            "SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved "
            "FROM generated_content WHERE date(created_at) = date('now', '-1 day')"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


# --- Config Changes ---

async def save_config_change(
    file_path: str, action: str, old_value: str, new_value: str
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO config_changes (file_path, action, old_value, new_value) VALUES (?, ?, ?, ?)",
            (file_path, action, old_value, new_value),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def confirm_config_change(change_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE config_changes SET confirmed = TRUE WHERE id = ?", (change_id,)
        )
        await db.commit()
    finally:
        await db.close()


async def get_last_config_change():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM config_changes WHERE confirmed = TRUE ORDER BY id DESC LIMIT 1"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def get_config_change_by_id(change_id: int):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM config_changes WHERE id = ?", (change_id,)
        )
        return await cursor.fetchone()
    finally:
        await db.close()
