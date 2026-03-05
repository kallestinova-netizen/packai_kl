import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import TELEGRAM_BOT_TOKEN
from src.bot.commands import router as commands_router
from src.bot.callbacks import router as callbacks_router
from src.bot.middleware import AdminOnlyMiddleware

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(token=TELEGRAM_BOT_TOKEN)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Register middleware
    dp.message.middleware(AdminOnlyMiddleware())

    # Register routers (callbacks first so format/action handlers take priority)
    dp.include_router(callbacks_router)
    dp.include_router(commands_router)

    return dp
