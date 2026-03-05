import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from src.config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if user_id not in ADMIN_USER_IDS:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            await event.answer("⛔ Доступ ограничен. Этот бот работает только для администратора.")
            return

        return await handler(event, data)
