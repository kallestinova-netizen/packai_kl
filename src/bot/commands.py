import json
import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from src.bot.callbacks import (
    EditStates,
    get_format_keyboard,
    get_news_keyboard,
    get_config_confirm_keyboard,
)
from src.modules.content_generator import generate_post, classify_voice_message, edit_post
from src.modules.transcriber import transcribe_voice
from src.modules.news_parser import parse_all_feeds
from src.db.queries import (
    get_todays_news,
    get_todays_plan_post,
    get_yesterday_stats,
    get_stats_week,
    get_stats_month,
    get_stats_by_rubric,
    get_stats_by_format,
    get_all_plan_posts,
    save_generated_content,
    update_content_text,
    get_content_by_id,
    log_activity,
    save_config_change,
    get_last_config_change,
)
from src.config import load_prompt, load_json_config, load_topic_bank, save_topic_bank, CONFIG_DIR, DATA_DIR

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await log_activity("command", "/start")
    text = (
        "👋 Привет! Я — AI-ассистент PACKAI.\n\n"
        "Помогаю создавать контент для LinkedIn, Telegram, Threads и блога.\n\n"
        "📋 **Команды:**\n"
        "☀️ /morning — утренняя сводка\n"
        "✍️ /create — создать пост (+ текст или голосовое)\n"
        "📈 /trend — тренды (скоро)\n"
        "📊 /stats — статистика\n"
        "📅 /plan — контент-план\n\n"
        "💡 Можешь просто отправить текст или голосовое — я сгенерирую пост!"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("morning"))
async def cmd_morning(message: Message):
    await log_activity("command", "/morning")
    await message.answer("☀️ Собираю утреннюю сводку...")

    # News
    news = await get_todays_news(limit=3)
    if not news:
        # Try parsing if no news today
        await parse_all_feeds()
        news = await get_todays_news(limit=3)

    news_text = "📰 **НОВОСТИ ДНЯ:**\n\n"
    if news:
        for i, item in enumerate(news, 1):
            news_text += f"{i}. **{item['title']}**\n"
            news_text += f"   📌 {item['summary'][:200]}\n"
            news_text += f"   🔗 {item['source']}\n\n"
            await message.answer(
                f"📰 **{i}. {item['title']}**\n\n{item['summary']}\n\n🔗 Источник: {item['source']}",
                reply_markup=get_news_keyboard(item["id"]),
                parse_mode="Markdown",
            )
    else:
        await message.answer("📰 Новостей по вашим темам сегодня не найдено.")

    # Content plan post
    plan_post = await get_todays_plan_post()
    if plan_post:
        content_id = await save_generated_content(
            source_type="plan",
            source_id=plan_post["id"],
            rubric=plan_post["rubric"] or "personal",
            format_name="linkedin",
            text=plan_post["full_text"],
        )
        await message.answer(
            f"📋 **ПОСТ ДНЯ** (из контент-плана):\n\n{plan_post['full_text']}",
            reply_markup=get_format_keyboard(content_id),
            parse_mode="Markdown",
        )
    else:
        await message.answer("📋 На сегодня постов в контент-плане нет.")

    # Yesterday stats
    yesterday = await get_yesterday_stats()
    created = yesterday["created"] if yesterday else 0
    approved = yesterday["approved"] if yesterday else 0
    await message.answer(f"📊 Вчера: {created} создано, {approved} одобрено")


@router.message(Command("create"))
async def cmd_create(message: Message):
    await log_activity("command", "/create")

    text = message.text.replace("/create", "", 1).strip()
    if not text:
        await message.answer(
            "✍️ Отправь текст после команды /create или просто голосовое сообщение.\n\n"
            "Пример: `/create AI-бот заменил контент-менеджера: кейс из практики`",
            parse_mode="Markdown",
        )
        return

    await message.answer("⏳ Генерирую пост...")
    post_text = await generate_post(topic=text, format_name="linkedin", rubric="situational")

    content_id = await save_generated_content(
        source_type="manual",
        source_id=0,
        rubric="situational",
        format_name="linkedin",
        text=post_text,
    )

    await log_activity("create", "/create", f"content_id={content_id}")
    keyboard = get_format_keyboard(content_id)
    await message.answer(post_text, reply_markup=keyboard)


@router.message(Command("trend"))
async def cmd_trend(message: Message):
    await log_activity("command", "/trend")
    await message.answer(
        "📈 Функция трендов будет доступна в следующем обновлении.\n\n"
        "В Неделе 3 здесь появится анализ трендов за последние 30 дней."
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    await log_activity("command", "/stats")

    week = await get_stats_week()
    month = await get_stats_month()
    by_rubric = await get_stats_by_rubric()
    by_format = await get_stats_by_format()

    week_total = week["total"] if week else 0
    week_approved = week["approved"] if week else 0
    week_rejected = week["rejected"] if week else 0
    month_total = month["total"] if month else 0
    month_approved = month["approved"] if month else 0
    month_rejected = month["rejected"] if month else 0

    text = (
        "📊 **СТАТИСТИКА**\n\n"
        f"**За неделю:**\n"
        f"  Создано: {week_total}\n"
        f"  ✅ Одобрено: {week_approved}\n"
        f"  ❌ Отклонено: {week_rejected}\n\n"
        f"**За месяц:**\n"
        f"  Создано: {month_total}\n"
        f"  ✅ Одобрено: {month_approved}\n"
        f"  ❌ Отклонено: {month_rejected}\n\n"
    )

    if by_rubric:
        text += "**По рубрикам (месяц):**\n"
        rubric_labels = {
            "newsroom": "📰 AI Newsroom",
            "howto": "🔧 How-To Lab",
            "personal": "👤 Personal Brand",
            "situational": "⚡ Situational",
        }
        for row in by_rubric:
            label = rubric_labels.get(row["rubric"], row["rubric"] or "—")
            text += f"  {label}: {row['count']}\n"
        text += "\n"

    if by_format:
        text += "**По форматам (месяц):**\n"
        format_labels = {
            "linkedin": "📝 LinkedIn",
            "telegram": "💬 Telegram",
            "threads": "🧵 Threads",
            "blog": "📰 Блог",
        }
        for row in by_format:
            label = format_labels.get(row["format"], row["format"] or "—")
            text += f"  {label}: {row['count']}\n"

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("plan"))
async def cmd_plan(message: Message):
    await log_activity("command", "/plan")

    posts = await get_all_plan_posts()
    if not posts:
        await message.answer("📅 Контент-план пуст. Добавьте посты через базу данных.")
        return

    text = "📅 **КОНТЕНТ-ПЛАН**\n\n"
    status_icons = {"published": "✅", "ready": "⏳", "missed": "❌", "draft": "📝"}

    for post in posts:
        icon = status_icons.get(post["status"], "⏳")
        date_str = post["scheduled_date"] or "—"
        rubric = post["rubric"] or ""
        text += f"{icon} **{date_str}** | {rubric} | {post['title']}\n"

    await message.answer(text, parse_mode="Markdown")


# --- Voice message handler ---

@router.message(F.voice)
async def handle_voice(message: Message):
    await log_activity("voice", "voice_message")
    await message.answer("🎤 Обрабатываю голосовое сообщение...")

    bot = message.bot
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_data = file_bytes.read()

    transcript = await transcribe_voice(audio_data)
    await message.answer(f"📝 Распознано:\n\n_{transcript}_", parse_mode="Markdown")

    # Classify: command or content?
    classification = await classify_voice_message(transcript)

    if classification["type"] == "command":
        await _handle_voice_command(message, classification)
    else:
        await _handle_voice_content(message, classification.get("text", transcript))


async def _handle_voice_command(message: Message, classification: dict):
    action = classification.get("action", "")
    target = classification.get("target", "")
    content = classification.get("content", "")
    summary = classification.get("summary", "")

    # Determine file path
    file_path = _resolve_config_path(action, target)
    if not file_path:
        await message.answer("❌ Не удалось определить файл для изменения.")
        return

    # Read current value
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            old_value = f.read()
    except FileNotFoundError:
        old_value = ""

    # Prepare new value (for now, store the instruction; actual change happens on confirm)
    new_value = content

    # If it's a JSON file, try to apply the change
    if file_path.endswith(".json"):
        try:
            current_data = json.loads(old_value) if old_value else {}
            new_value = _apply_json_change(action, current_data, content)
            new_value = json.dumps(new_value if isinstance(new_value, (dict, list)) else current_data, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to prepare JSON change: {e}")

    change_id = await save_config_change(file_path, action, old_value, new_value)

    keyboard = get_config_confirm_keyboard(change_id)
    await message.answer(
        f"🔧 Поняла! Хочешь изменить:\n\n"
        f"📁 Файл: `{file_path}`\n"
        f"✏️ Изменение: {summary}\n",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _handle_voice_content(message: Message, text: str):
    await message.answer("⏳ Генерирую пост из голосового...")

    post_text = await generate_post(topic=text, format_name="linkedin", rubric="situational")
    content_id = await save_generated_content(
        source_type="voice",
        source_id=0,
        rubric="situational",
        format_name="linkedin",
        text=post_text,
    )

    await log_activity("voice_create", "voice", f"content_id={content_id}")
    keyboard = get_format_keyboard(content_id)
    await message.answer(post_text, reply_markup=keyboard)


# --- Text message handler (no command) ---

@router.message(EditStates.waiting_for_edit)
async def handle_edit_text(message: Message, state: FSMContext):
    data = await state.get_data()
    content_id = data.get("edit_content_id")
    await state.clear()

    if not content_id:
        await message.answer("❌ Ошибка: не найден пост для редактирования.")
        return

    content = await get_content_by_id(content_id)
    if not content:
        await message.answer("❌ Контент не найден.")
        return

    await message.answer("⏳ Редактирую пост...")

    new_text = await edit_post(
        original_text=content["text"],
        edit_instructions=message.text,
        format_name=content["format"] or "linkedin",
    )

    new_id = await save_generated_content(
        source_type="edit",
        source_id=content_id,
        rubric=content["rubric"] or "situational",
        format_name=content["format"] or "linkedin",
        text=new_text,
    )

    await log_activity("edit", "act:edit", f"content_id={content_id} -> {new_id}")
    keyboard = get_format_keyboard(new_id)
    await message.answer(
        f"✏️ Отредактированная версия:\n\n{new_text}",
        reply_markup=keyboard,
    )


@router.message(F.text)
async def handle_free_text(message: Message):
    text = message.text.strip()
    if not text:
        return

    # Check for rollback command
    if "откати последнее изменение" in text.lower():
        await _handle_rollback(message)
        return

    await log_activity("free_text", "text", f"len={len(text)}")
    await message.answer("⏳ Генерирую пост...")

    post_text = await generate_post(topic=text, format_name="linkedin", rubric="situational")

    content_id = await save_generated_content(
        source_type="text",
        source_id=0,
        rubric="situational",
        format_name="linkedin",
        text=post_text,
    )

    await log_activity("text_create", "text", f"content_id={content_id}")
    keyboard = get_format_keyboard(content_id)
    await message.answer(post_text, reply_markup=keyboard)


async def _handle_rollback(message: Message):
    change = await get_last_config_change()
    if not change:
        await message.answer("❌ Нет изменений для отката.")
        return

    file_path = change["file_path"]
    old_value = change["old_value"]

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(old_value)
        await log_activity("rollback", "rollback", f"file={file_path}, change_id={change['id']}")
        await message.answer(f"↩️ Откатила изменение в файле `{file_path}`.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        await message.answer(f"❌ Ошибка при откате: {e}")


def _resolve_config_path(action: str, target: str) -> str:
    mapping = {
        "update_prompt": "config/prompts/",
        "update_style": "config/prompts/system_base.txt",
        "add_case": "config/profile.json",
        "add_topic": "data/topic-bank.json",
        "add_source": "config/sources.json",
        "add_keyword": "config/keywords.json",
    }

    if action == "update_prompt":
        # Try to match target to a prompt file
        prompt_files = ["system_base.txt", "linkedin.txt", "telegram.txt", "threads.txt", "blog_seo.txt", "video_script.txt"]
        for pf in prompt_files:
            if any(keyword in target.lower() for keyword in [pf.replace(".txt", "").replace("_", " ")]):
                return f"config/prompts/{pf}"
        return "config/prompts/system_base.txt"

    return mapping.get(action, "")


def _apply_json_change(action: str, data: dict, content: str):
    if action == "add_topic":
        if "howto" in data:
            data["howto"].append({"title": content, "tags": [], "used": False})
        return data
    elif action == "add_source":
        if "rss" in data:
            data["rss"].append({"name": content, "url": ""})
        return data
    elif action == "add_keyword":
        if "secondary" in data:
            data["secondary"].append(content)
        return data
    elif action == "add_case":
        if "cases" in data:
            data["cases"].append({"client": "", "description": content, "result": "", "quote": ""})
        return data
    return data
