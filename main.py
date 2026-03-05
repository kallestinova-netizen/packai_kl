import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import LOG_DIR
from src.db.queries import init_db
from src.bot.app import create_bot, create_dispatcher
from src.scheduler.cron import setup_scheduler


def setup_logging():
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "bot.log", encoding="utf-8"),
        ],
    )


async def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Configuring scheduler...")
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler configured.")

    logger.info("Bot started, scheduler configured, database initialized.")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
