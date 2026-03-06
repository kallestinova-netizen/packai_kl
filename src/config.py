import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", BASE_DIR / "config"))
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = CONFIG_DIR / "prompts"
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", DATA_DIR / "backups"))

# Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_IDS = json.loads(os.getenv("ADMIN_USER_IDS", "[]"))

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "bot.db"))

# Timezone
TZ = os.getenv("TZ", "Asia/Novosibirsk")


def load_json_config(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_config(filename: str, data: dict):
    path = CONFIG_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_prompt(name: str, content: str):
    path = PROMPTS_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def load_profile() -> dict:
    return load_json_config("profile.json")


def load_brand() -> dict:
    return load_json_config("brand.json")


def load_keywords() -> dict:
    return load_json_config("keywords.json")


def load_sources() -> dict:
    return load_json_config("sources.json")


def load_schedule() -> dict:
    return load_json_config("schedule.json")


def load_content_plan() -> list:
    path = DATA_DIR / "content-plan.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_content_plan(data: list):
    path = DATA_DIR / "content-plan.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_topic_bank() -> dict:
    path = DATA_DIR / "topic-bank.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_topic_bank(data: dict):
    path = DATA_DIR / "topic-bank.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
