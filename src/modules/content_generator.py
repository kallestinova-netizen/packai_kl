import json
import logging
from anthropic import AsyncAnthropic
from src.config import ANTHROPIC_API_KEY, load_prompt, load_profile
from src.utils.text_cleaner import clean_markdown

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client

FORMAT_PROMPTS = {
    "linkedin": "linkedin.txt",
    "telegram": "telegram.txt",
    "threads": "threads.txt",
    "blog": "blog_seo.txt",
}


async def generate_post(
    topic: str,
    format_name: str = "linkedin",
    rubric: str = "situational",
    extra_context: str = "",
) -> str:
    system_prompt = load_prompt("system_base.txt")
    profile = load_profile()

    profile_context = (
        f"Профиль: {profile['name']}, {profile['role']}, {profile['company']}\n"
        f"Tagline: {profile['tagline']}\n"
        f"USP: {', '.join(profile['usp'])}\n"
    )

    format_prompt = load_prompt(FORMAT_PROMPTS.get(format_name, "linkedin.txt"))

    rubric_instruction = _get_rubric_instruction(rubric)

    user_message = (
        f"{format_prompt}\n\n"
        f"Рубрика: {rubric}\n"
        f"{rubric_instruction}\n\n"
        f"Тема/контекст: {topic}\n"
    )
    if extra_context:
        user_message += f"\nДополнительный контекст: {extra_context}\n"

    response = await _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=f"{system_prompt}\n\n{profile_context}",
        messages=[{"role": "user", "content": user_message}],
    )

    return clean_markdown(response.content[0].text)


async def generate_news_post(title: str, summary: str, source: str, format_name: str = "linkedin") -> str:
    return await generate_post(
        topic=f"Новость: {title}\nИсточник: {source}\nСуть: {summary}",
        format_name=format_name,
        rubric="newsroom",
    )


async def regenerate_post(topic: str, format_name: str, rubric: str) -> str:
    return await generate_post(topic=topic, format_name=format_name, rubric=rubric)


async def edit_post(original_text: str, edit_instructions: str, format_name: str) -> str:
    system_prompt = load_prompt("system_base.txt")
    format_prompt = load_prompt(FORMAT_PROMPTS.get(format_name, "linkedin.txt"))

    user_message = (
        f"{format_prompt}\n\n"
        f"Вот оригинальный пост:\n{original_text}\n\n"
        f"Правки от автора: {edit_instructions}\n\n"
        f"Перепиши пост с учётом правок. Верни только итоговый текст."
    )

    response = await _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return clean_markdown(response.content[0].text)


async def classify_voice_message(text: str) -> dict:
    prompt = (
        "Проанализируй текст голосового сообщения.\n\n"
        "Если это команда на изменение настроек бота (начинается со слов: "
        "измени, добавь, удали, обнови, поменяй, убери) — верни JSON:\n"
        '{"type": "command", "action": "update_prompt|add_case|add_topic|add_source|update_style|add_keyword", '
        '"target": "имя файла", "content": "что именно изменить", "summary": "краткое описание изменения"}\n\n'
        "Если это контент для поста — верни JSON:\n"
        '{"type": "content", "text": "транскрибированный текст"}\n\n'
        f"Текст: {text}\n\n"
        "Верни ТОЛЬКО JSON, без пояснений."
    )

    response = await _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = response.content[0].text.strip()
    # Extract JSON from response
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    return json.loads(result_text)


async def filter_news_with_ai(title: str, description: str, source: str) -> dict:
    """Use AI to filter news relevance using news_filter.txt prompt."""
    try:
        filter_prompt = load_prompt("news_filter.txt")
    except FileNotFoundError:
        return {"relevant": True, "score": 50}

    user_message = (
        f"Источник: {source}\n"
        f"Заголовок: {title}\n"
        f"Описание: {description}"
    )

    response = await _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=filter_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    result_text = response.content[0].text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    return json.loads(result_text)


async def generate_news_summary(title: str, description: str) -> str:
    response = await _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Кратко перескажи новость на русском языке в 2-3 предложения. "
                    f"Фокус на практическую пользу для маркетолога.\n\n"
                    f"Заголовок: {title}\n"
                    f"Описание: {description}"
                ),
            }
        ],
    )
    return clean_markdown(response.content[0].text)


def _get_rubric_instruction(rubric: str) -> str:
    instructions = {
        "newsroom": (
            "AI Newsroom — пост на основе актуальной новости из мира AI/маркетинга. "
            "Формат: что произошло → почему это важно → что это значит для предпринимателя."
        ),
        "howto": (
            "How-To Lab — пост-инструкция. "
            "Формат: кто внедрил → что внедрили → цифры до/после → как повторить → вывод."
        ),
        "personal": (
            "Personal Brand — личный пост от Натальи. "
            "Типы: реалити (дневник PACKAI), экспертный (уроки из опыта), кейс (клиент + результат), ценности."
        ),
        "situational": (
            "Situational & Trending — ситуационный пост на основе мысли, идеи или события. "
            "Оформи как экспертный комментарий или размышление."
        ),
    }
    return instructions.get(rubric, instructions["situational"])
