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

    prompt = """Ты — новостной редактор для маркетолога-практика, специалиста по AI-автоматизации маркетинга.

Найди 5 новостей за последние 48 часов СТРОГО по критериям:

ОБЯЗАТЕЛЬНО (каждая новость должна соответствовать минимум 2):
1. Конкретные цифры: рост выручки X%, экономия $X, конверсия +X%, пользователей X тысяч
2. Реальный кейс компании: кто внедрил AI в маркетинг/продажи и какой измеримый результат
3. Запуск AI-инструмента для маркетинга/контента/продаж С ЦЕНОЙ
4. Обновление рекламных платформ (Meta Ads, Google Ads, TikTok Ads, VK Ads, Яндекс Директ) с влиянием на рекламодателей
5. Creator economy: монетизация AI-аватаров, автоматизация контента, цифровые двойники С ЦИФРАМИ сделки
6. AI-стартап из Y Combinator в сфере маркетинга/продаж с метриками роста

НЕ ПОДХОДИТ (отклоняй сразу):
- Общие новости про AI без маркетингового применения (типа Microsoft объединился с Anthropic)
- Новости без конкретных цифр и метрик
- Технические обновления моделей без бизнес-импакта
- Мнения и прогнозы без данных
- Новости про безопасность AI, этику, регулирование

ПРИМЕРЫ ИДЕАЛЬНЫХ НОВОСТЕЙ:
- Starbucks внедрил AI-персонализацию: средний чек вырос на 34%
- TikTok-инфлюенсер сдал цифрового двойника в аренду за $900M
- Meta выкатила AI-генератор рекламы: первые тесты показали 3x рост конверсий
- HubSpot добавил AI-ассистента: пользователи создают контент на 67% быстрее
- YC стартап Jasper AI достиг $100M ARR за 18 месяцев

Верни ТОЛЬКО JSON массив без markdown:
[{"title": "заголовок на русском", "summary": "2-3 предложения с конкретными цифрами на русском", "source": "название источника", "url": "ссылка", "score": 50-100, "video_potential": "высокий/средний/низкий"}]

Если за 48 часов нет новостей соответствующих критериям — верни пустой массив []. Лучше 0 новостей чем мусор."""

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
