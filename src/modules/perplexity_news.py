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

    from datetime import date
    today = date.today().isoformat()

    prompt = f"Today is {today}. Find 5 fresh news from last 3 days about AI in marketing and business. Sources: TechCrunch, The Verge, Marketing Brew, Search Engine Land, HubSpot, Adweek, Product Hunt, Social Media Today, Martech.org. Topics: new AI marketing tools with pricing, companies using AI with metrics and ROI, ad platform updates Meta Google TikTok VK, AI startups with funding, creator economy AI avatars automation. Do NOT include: news older than 3 days, ethics or safety AI news, technical model updates without business impact. Return ONLY a JSON array no text before or after. Always exactly 5 items. Format: " + '[{"title": "title in Russian", "summary": "2-3 sentences in Russian", "source": "source", "url": "link", "score": 70, "video_potential": "medium"}]'

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
