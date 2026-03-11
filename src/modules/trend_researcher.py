import os
import json
import asyncio
import logging
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
LAST30DAYS_SCRIPT = Path(__file__).parent.parent.parent / "skills" / "last30days" / "scripts" / "last30days.py"


async def discover_emerging_trends() -> list[dict]:
    """Find 3 emerging trends via Perplexity API."""

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    prompt = (
        "You are a trend scout for a marketing professional. "
        "Find 3 EMERGING trends that are just starting to gain traction in the last 7-14 days "
        "across Reddit, X/Twitter, YouTube, Hacker News in these areas: advertising, marketing, "
        "content creation, AI tools for business. "
        "Look for topics with sudden spike in discussions, not established trends everyone knows about. "
        "Focus on: new tools nobody heard of a month ago, unexpected AI use cases in marketing, "
        "viral strategies that are just starting, new platform features marketers haven't adopted yet.\n\n"
        "Return ONLY JSON array without markdown:\n"
        '[{"topic": "topic in English for research", "title_ru": "заголовок на русском", '
        '"signal": "where the spike is: Reddit/X/YouTube/HN", '
        '"why_emerging": "почему это зарождающийся тренд на русском"}]'
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
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


async def research_trend(topic: str) -> dict | None:
    """Deep research a topic via last30days. Returns None on failure (no fallback)."""

    if not LAST30DAYS_SCRIPT.exists():
        logger.error(f"last30days script not found: {LAST30DAYS_SCRIPT}")
        return None

    env = os.environ.copy()
    # Ensure keys are available for last30days
    for key in ("OPENAI_API_KEY", "XAI_API_KEY"):
        if key not in env:
            val = os.getenv(key)
            if val:
                env[key] = val

    cmd = ["python3", str(LAST30DAYS_SCRIPT), topic, "--emit=json", "--quick"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if proc.returncode != 0:
            logger.error(f"last30days failed (exit {proc.returncode}): {stderr.decode()[:500]}")
            return None

        raw = stdout.decode().strip()
        if not raw:
            logger.error("last30days returned empty output")
            return None

        data = json.loads(raw)
        return _parse_last30days(topic, data)

    except asyncio.TimeoutError:
        logger.error(f"last30days timed out after 180s for topic: {topic}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"last30days returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"last30days failed: {e}")
        return None


def _parse_last30days(topic: str, data: dict) -> dict:
    """Parse last30days JSON output into a structured result."""

    reddit_items = data.get("reddit", [])
    x_items = data.get("x", data.get("twitter", []))
    youtube_items = data.get("youtube", [])

    reddit_count = len(reddit_items)
    reddit_upvotes = sum(item.get("score", item.get("upvotes", 0)) for item in reddit_items)
    x_count = len(x_items)
    x_likes = sum(item.get("likes", item.get("favorites", 0)) for item in x_items)
    youtube_count = len(youtube_items)

    # Top items
    top_reddit = {}
    if reddit_items:
        top = max(reddit_items, key=lambda i: i.get("score", i.get("upvotes", 0)))
        top_reddit = {
            "title": top.get("title", ""),
            "upvotes": top.get("score", top.get("upvotes", 0)),
            "url": top.get("url", ""),
        }

    top_x = {}
    if x_items:
        top = max(x_items, key=lambda i: i.get("likes", i.get("favorites", 0)))
        top_x = {
            "text": (top.get("text", ""))[:200],
            "likes": top.get("likes", top.get("favorites", 0)),
            "reposts": top.get("reposts", top.get("retweets", 0)),
        }

    top_youtube = {}
    if youtube_items:
        top = max(youtube_items, key=lambda i: i.get("views", i.get("view_count", 0)))
        top_youtube = {
            "title": top.get("title", ""),
            "views": top.get("views", top.get("view_count", 0)),
            "url": top.get("url", ""),
        }

    # Extract insights from data
    key_insights = data.get("key_insights", data.get("insights", []))
    if not key_insights:
        # Build insights from top content
        insights = []
        if top_reddit:
            insights.append(f"Reddit: {top_reddit['title']}")
        if top_x:
            insights.append(f"X: {top_x['text'][:100]}")
        if top_youtube:
            insights.append(f"YouTube: {top_youtube['title']}")
        key_insights = insights[:3]

    summary = data.get("summary", "")
    post_idea = data.get("post_idea", data.get("recommendation", ""))

    return {
        "topic": topic,
        "summary": summary,
        "reddit_count": reddit_count,
        "reddit_upvotes": reddit_upvotes,
        "x_count": x_count,
        "x_likes": x_likes,
        "youtube_count": youtube_count,
        "key_insights": key_insights[:5],
        "top_reddit": top_reddit,
        "top_x": top_x,
        "top_youtube": top_youtube,
        "post_idea": post_idea,
    }
