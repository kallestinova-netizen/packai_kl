import os
import json
import logging

import aiohttp

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


async def fetch_news_via_perplexity() -> list[dict]:
    """Ищет новости через Perplexity API с живого веба."""

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY not set, skipping Perplexity news fetch")
        return []

    prompt = """Найди 5 самых важных новостей за последние 24 часа по критериям:

ИСТОЧНИКИ: martech.org, techcrunch.com, sostav.ru, cossa.ru, businessinsider.com, theverge.com, ycombinator.com, hubspot.com, searchengineland.com

КРИТЕРИИ (минимум 2):
- Запуск нового AI-инструмента для маркетинга с ценой
- Кейс с метриками: рост >30%, конверсии, пользователи >100K
- Обновление крупной платформы: Meta, Google, Яндекс, VK, TikTok
- Creator economy + AI: аватары, автоматизация, цифровые двойники
- AI-стартапы из Y Combinator
- Рекордная сделка >$50M или результат кампании >50% роста

НЕ ВКЛЮЧАЙ: технические исследования без бизнес-импакта, мнения без данных, арт/мемы

Верни ТОЛЬКО JSON массив (без markdown, без пояснений):
[
  {
    "title": "заголовок на русском",
    "summary": "описание 2-3 предложения на русском",
    "source": "название источника",
    "url": "ссылка",
    "score": число 0-100,
    "video_potential": "высокий/средний/низкий"
  }
]"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PERPLEXITY_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Perplexity API returned status {resp.status}")
                    return []

                data = await resp.json()
                text = data["choices"][0]["message"]["content"]

                # Очистить от markdown если есть
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]

                return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Perplexity returned invalid JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Perplexity API call failed: {e}")
        return []
