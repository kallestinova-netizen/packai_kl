import os
import json
import logging

import aiohttp

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


async def research_trend(topic: str) -> dict:
    """Research a topic using Perplexity API across social platforms and web."""

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    prompt = f"""Research the topic '{topic}' across Reddit, X/Twitter, YouTube, Hacker News and the web from the last 30 days. Find what people are actually discussing, upvoting, sharing.

Return ONLY a JSON object without markdown:
{{"topic": "тема на русском", "summary": "обзор 3-5 предложений на русском что обсуждают", "key_insights": ["инсайт 1", "инсайт 2", "инсайт 3"], "trending_tools": ["инструмент 1", "инструмент 2"], "best_practices": ["практика 1", "практика 2"], "post_idea": "идея для поста на основе тренда на русском", "sources": ["источник 1", "источник 2"]}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Perplexity API returned status {resp.status}")

            data = await resp.json()
            text = data["choices"][0]["message"]["content"]

            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]

            return json.loads(text)
