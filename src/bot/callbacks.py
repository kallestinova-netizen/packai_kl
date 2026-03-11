import json
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram.types import FSInputFile

from src.modules.content_generator import generate_post, generate_news_post, generate_video_script, edit_post
from src.modules.image_generator import generate_post_image
from src.db.queries import (
    get_content_by_id,
    get_news_by_id,
    update_content_status,
    update_content_text,
    save_generated_content,
    save_generated_image,
    get_image_by_id,
    log_activity,
    save_config_change,
    confirm_config_change,
    get_config_change_by_id,
    get_plan_post_number,
)
from src.config import load_prompt, save_prompt, load_json_config, save_json_config

logger = logging.getLogger(__name__)
router = Router()


class EditStates(StatesGroup):
    waiting_for_edit = State()


def get_format_keyboard(content_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 LinkedIn", callback_data=f"fmt:linkedin:{content_id}"),
                InlineKeyboardButton(text="💬 Telegram", callback_data=f"fmt:telegram:{content_id}"),
                InlineKeyboardButton(text="🧵 Threads", callback_data=f"fmt:threads:{content_id}"),
                InlineKeyboardButton(text="📰 Блог", callback_data=f"fmt:blog:{content_id}"),
            ],
            [
                InlineKeyboardButton(text="🖼 Картинка", callback_data=f"img:select:{content_id}"),
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"act:approve:{content_id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"act:edit:{content_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Заново", callback_data=f"act:regen:{content_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"act:reject:{content_id}"),
            ],
        ]
    )


def get_news_keyboard(news_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 LinkedIn", callback_data=f"news:linkedin:{news_id}"),
                InlineKeyboardButton(text="💬 Telegram", callback_data=f"news:telegram:{news_id}"),
                InlineKeyboardButton(text="🧵 Threads", callback_data=f"news:threads:{news_id}"),
                InlineKeyboardButton(text="📰 Блог", callback_data=f"news:blog:{news_id}"),
                InlineKeyboardButton(text="🎬 Скрипт", callback_data=f"news:video:{news_id}"),
            ],
        ]
    )


def get_trend_keyboard(post_idea: str) -> InlineKeyboardMarkup:
    # Telegram callback_data limit is 64 bytes, so we use a marker
    # and extract the post idea from the message text in the handler
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Создать пост", callback_data="trend:post"),
                InlineKeyboardButton(text="🎬 Скрипт", callback_data="trend:video"),
            ],
        ]
    )


def get_config_confirm_keyboard(change_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"cfg:confirm:{change_id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"cfg:cancel:{change_id}"),
                InlineKeyboardButton(text="👁 Показать текущий", callback_data=f"cfg:show:{change_id}"),
            ],
        ]
    )


# --- Format callbacks ---

@router.callback_query(F.data.startswith("fmt:"))
async def on_format_callback(callback: CallbackQuery):
    _, format_name, content_id_str = callback.data.split(":")
    content_id = int(content_id_str)

    await callback.answer(f"Генерирую формат {format_name}...")

    content = await get_content_by_id(content_id)
    if not content:
        await callback.message.answer("❌ Контент не найден.")
        return

    original_text = content["text"]
    rubric = content["rubric"] or "situational"

    # Get post_number if content originated from content plan
    post_number = 0
    if content["source_type"] == "plan" and content["source_id"]:
        post_number = await get_plan_post_number(content["source_id"])

    new_text = await generate_post(
        topic=original_text,
        format_name=format_name,
        rubric=rubric,
        post_number=post_number,
    )

    new_id = await save_generated_content(
        source_type="reformat",
        source_id=content_id,
        rubric=rubric,
        format_name=format_name,
        text=new_text,
    )

    await log_activity("format", f"fmt:{format_name}", f"content_id={content_id} -> {new_id}")

    keyboard = get_format_keyboard(new_id)
    format_labels = {"linkedin": "📝 LinkedIn", "telegram": "💬 Telegram", "threads": "🧵 Threads", "blog": "📰 Блог"}
    label = format_labels.get(format_name, format_name)

    await callback.message.answer(
        f"{label}\n\n{new_text}",
        reply_markup=keyboard,
    )


# --- News format callbacks ---

@router.callback_query(F.data.startswith("news:"))
async def on_news_format_callback(callback: CallbackQuery):
    _, format_name, news_id_str = callback.data.split(":")
    news_id = int(news_id_str)

    news = await get_news_by_id(news_id)
    if not news:
        await callback.message.answer("❌ Новость не найдена.")
        return

    # Video script generation
    if format_name == "video":
        await callback.answer("🎬 Генерирую видео-скрипт...")
        try:
            script = await generate_video_script(
                title=news["title"],
                summary=news["summary"],
                source=news["source"],
            )
            await log_activity("video_script", f"news:video", f"news_id={news_id}")
            await callback.message.answer(f"🎬 ВИДЕО-СКРИПТ:\n\n{script}")
        except Exception as e:
            logger.error(f"Video script generation failed: {e}")
            await callback.message.answer(f"❌ Ошибка генерации скрипта: {e}")
        return

    await callback.answer(f"Генерирую пост из новости...")

    text = await generate_news_post(
        title=news["title"],
        summary=news["summary"],
        source=news["source"],
        format_name=format_name,
    )

    content_id = await save_generated_content(
        source_type="news",
        source_id=news_id,
        rubric="newsroom",
        format_name=format_name,
        text=text,
    )

    await log_activity("news_post", f"news:{format_name}", f"news_id={news_id}")

    keyboard = get_format_keyboard(content_id)
    await callback.message.answer(text, reply_markup=keyboard)


# --- Trend callbacks ---

@router.callback_query(F.data.startswith("trend:"))
async def on_trend_callback(callback: CallbackQuery):
    _, action = callback.data.split(":")

    # Extract post idea from the message text (after "ИДЕЯ ДЛЯ ПОСТА:")
    msg_text = callback.message.text or ""
    post_idea = ""
    if "ИДЕЯ ДЛЯ ПОСТА:" in msg_text:
        post_idea = msg_text.split("ИДЕЯ ДЛЯ ПОСТА:")[1].split("\n\nИсточники:")[0].strip()
    if not post_idea:
        # Fallback: use the topic from the first line
        post_idea = msg_text.split("\n")[0].replace("ТРЕНД:", "").strip()

    if action == "post":
        await callback.answer("📝 Генерирую пост...")
        try:
            text = await generate_post(
                topic=post_idea,
                format_name="linkedin",
                rubric="situational",
            )
            content_id = await save_generated_content(
                source_type="trend",
                source_id=0,
                rubric="situational",
                format_name="linkedin",
                text=text,
            )
            await log_activity("trend_post", "trend:post", f"content_id={content_id}")
            keyboard = get_format_keyboard(content_id)
            await callback.message.answer(text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Trend post generation failed: {e}")
            await callback.message.answer(f"❌ Ошибка генерации поста: {e}")

    elif action == "video":
        await callback.answer("🎬 Генерирую видео-скрипт...")
        try:
            script = await generate_video_script(
                title=post_idea,
                summary=msg_text[:500],
                source="Trend Research",
            )
            await log_activity("trend_video", "trend:video")
            await callback.message.answer(f"🎬 ВИДЕО-СКРИПТ:\n\n{script}")
        except Exception as e:
            logger.error(f"Trend video script failed: {e}")
            await callback.message.answer(f"❌ Ошибка генерации скрипта: {e}")


# --- Action callbacks ---

@router.callback_query(F.data.startswith("act:"))
async def on_action_callback(callback: CallbackQuery, state: FSMContext):
    _, action, content_id_str = callback.data.split(":")
    content_id = int(content_id_str)

    if action == "approve":
        await update_content_status(content_id, "approved")
        await log_activity("approve", "act:approve", f"content_id={content_id}")
        await callback.answer("✅ Одобрено!")
        await callback.message.answer("✅ Пост одобрен и сохранён.")

    elif action == "reject":
        await update_content_status(content_id, "rejected")
        await log_activity("reject", "act:reject", f"content_id={content_id}")
        await callback.answer("❌ Отклонено")
        await callback.message.answer("❌ Пост отклонён.")

    elif action == "edit":
        await state.set_state(EditStates.waiting_for_edit)
        await state.update_data(edit_content_id=content_id)
        await callback.answer()
        await callback.message.answer(
            "✏️ Напиши или отправь голосовое — что нужно изменить в посте. Я перепишу с учётом твоих правок."
        )

    elif action == "regen":
        await callback.answer("🔄 Перегенерирую...")
        content = await get_content_by_id(content_id)
        if not content:
            await callback.message.answer("❌ Контент не найден.")
            return

        new_text = await generate_post(
            topic=content["text"],
            format_name=content["format"] or "linkedin",
            rubric=content["rubric"] or "situational",
        )

        new_id = await save_generated_content(
            source_type="regen",
            source_id=content_id,
            rubric=content["rubric"] or "situational",
            format_name=content["format"] or "linkedin",
            text=new_text,
        )

        await log_activity("regen", "act:regen", f"content_id={content_id} -> {new_id}")
        keyboard = get_format_keyboard(new_id)
        await callback.message.answer(
            f"🔄 Новая версия:\n\n{new_text}",
            reply_markup=keyboard,
        )


# --- Config change callbacks ---

@router.callback_query(F.data.startswith("cfg:"))
async def on_config_callback(callback: CallbackQuery):
    _, action, change_id_str = callback.data.split(":")
    change_id = int(change_id_str)

    change = await get_config_change_by_id(change_id)
    if not change:
        await callback.message.answer("❌ Изменение не найдено.")
        return

    if action == "confirm":
        file_path = change["file_path"]
        new_value = change["new_value"]

        if file_path.endswith(".txt"):
            save_prompt(file_path.split("/")[-1], new_value)
        elif file_path.endswith(".json"):
            data = json.loads(new_value)
            config_name = file_path.split("/")[-1]
            if "data/" in file_path:
                from src.config import save_topic_bank
                save_topic_bank(data)
            else:
                save_json_config(config_name, data)

        await confirm_config_change(change_id)
        await log_activity("config_change", "cfg:confirm", f"change_id={change_id}, file={file_path}")
        await callback.answer("✅ Изменения применены!")
        await callback.message.answer(f"✅ Файл {file_path} обновлён.")

    elif action == "cancel":
        await log_activity("config_cancel", "cfg:cancel", f"change_id={change_id}")
        await callback.answer("❌ Отменено")
        await callback.message.answer("❌ Изменение отменено.")

    elif action == "show":
        old_value = change["old_value"]
        await callback.answer()
        text = old_value if len(old_value) < 4000 else old_value[:4000] + "\n..."
        await callback.message.answer(f"📄 Текущее содержимое:\n\n{text}")


# --- Image callbacks ---

def get_image_format_keyboard(content_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 LinkedIn", callback_data=f"img:linkedin:{content_id}"),
                InlineKeyboardButton(text="💬 Telegram", callback_data=f"img:telegram:{content_id}"),
            ],
            [
                InlineKeyboardButton(text="🧵 Threads", callback_data=f"img:threads:{content_id}"),
                InlineKeyboardButton(text="📱 Stories", callback_data=f"img:stories:{content_id}"),
            ],
        ]
    )


def get_image_action_keyboard(image_id: int, content_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Использовать", callback_data=f"imgact:use:{image_id}"),
                InlineKeyboardButton(text="🔄 Заново", callback_data=f"imgact:regen:{image_id}:{content_id}"),
            ],
        ]
    )


@router.callback_query(F.data.startswith("img:"))
async def on_image_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    _, action, content_id_str = parts[0], parts[1], parts[2]
    content_id = int(content_id_str)

    if action == "select":
        # Show image format selection
        await callback.answer()
        await callback.message.answer(
            "🖼 Выбери формат картинки:",
            reply_markup=get_image_format_keyboard(content_id),
        )
        return

    # action is the image format (linkedin, telegram, threads, stories)
    image_format = action
    await callback.answer(f"🖼 Генерирую картинку {image_format}...")

    content = await get_content_by_id(content_id)
    if not content:
        await callback.message.answer("❌ Контент не найден.")
        return

    try:
        file_path = await generate_post_image(
            content_id=content_id,
            post_text=content["text"],
            image_format=image_format,
        )

        image_id = await save_generated_image(
            content_id=content_id,
            format_name=image_format,
            file_path=file_path,
        )

        await log_activity("image_gen", f"img:{image_format}", f"content_id={content_id}, image_id={image_id}")

        keyboard = get_image_action_keyboard(image_id, content_id)
        photo = FSInputFile(file_path)
        format_labels = {
            "linkedin": "📝 LinkedIn (1200x627)",
            "telegram": "💬 Telegram (1280x720)",
            "threads": "🧵 Threads (1080x1080)",
            "stories": "📱 Stories (1080x1920)",
        }
        label = format_labels.get(image_format, image_format)

        await callback.message.answer_photo(
            photo=photo,
            caption=f"🖼 {label}",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        await callback.message.answer(f"❌ Ошибка генерации картинки: {e}")


@router.callback_query(F.data.startswith("imgact:"))
async def on_image_action_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]

    if action == "use":
        image_id = int(parts[2])
        image = await get_image_by_id(image_id)
        if not image:
            await callback.message.answer("❌ Картинка не найдена.")
            return
        await log_activity("image_approve", "imgact:use", f"image_id={image_id}")
        await callback.answer("✅ Картинка сохранена!")
        await callback.message.answer(f"✅ Картинка сохранена: {image['file_path']}")

    elif action == "regen":
        image_id = int(parts[2])
        content_id = int(parts[3])

        image = await get_image_by_id(image_id)
        if not image:
            await callback.message.answer("❌ Картинка не найдена.")
            return

        await callback.answer("🔄 Перегенерирую картинку...")

        content = await get_content_by_id(content_id)
        if not content:
            await callback.message.answer("❌ Контент не найден.")
            return

        try:
            file_path = await generate_post_image(
                content_id=content_id,
                post_text=content["text"],
                image_format=image["format"],
            )

            new_image_id = await save_generated_image(
                content_id=content_id,
                format_name=image["format"],
                file_path=file_path,
            )

            await log_activity("image_regen", "imgact:regen", f"image_id={image_id} -> {new_image_id}")

            keyboard = get_image_action_keyboard(new_image_id, content_id)
            photo = FSInputFile(file_path)
            await callback.message.answer_photo(
                photo=photo,
                caption="🔄 Новая версия картинки",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Image regeneration failed: {e}")
            await callback.message.answer(f"❌ Ошибка перегенерации: {e}")
