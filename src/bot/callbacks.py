import json
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.modules.content_generator import generate_post, generate_news_post, edit_post
from src.db.queries import (
    get_content_by_id,
    get_news_by_id,
    update_content_status,
    update_content_text,
    save_generated_content,
    log_activity,
    save_config_change,
    confirm_config_change,
    get_config_change_by_id,
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
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"act:approve:{content_id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"act:edit:{content_id}"),
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

    new_text = await generate_post(
        topic=original_text,
        format_name=format_name,
        rubric=rubric,
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

    await callback.answer(f"Генерирую пост из новости...")

    news = await get_news_by_id(news_id)
    if not news:
        await callback.message.answer("❌ Новость не найдена.")
        return

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
            "✏️ Напиши, что нужно изменить в посте. Я перепишу с учётом твоих правок."
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
