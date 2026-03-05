import logging
import asyncio
import xml.etree.ElementTree as ET

import aiohttp
from Levenshtein import ratio as levenshtein_ratio

from src.config import load_sources, load_keywords
from src.db.queries import save_news, get_todays_news
from src.modules.content_generator import generate_news_summary

logger = logging.getLogger(__name__)


def parse_rss_xml(xml_text: str) -> list[dict]:
    """Parse RSS/Atom XML into a list of entries."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return entries

    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        if title:
            entries.append({"title": title, "link": link, "description": description})

    # Atom fallback
    if not entries:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry_el in root.findall(".//atom:entry", ns):
            title = (entry_el.findtext("atom:title", "", ns) or "").strip()
            link_el = entry_el.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = (entry_el.findtext("atom:summary", "", ns) or "").strip()
            content = (entry_el.findtext("atom:content", "", ns) or "").strip()
            if title:
                entries.append({"title": title, "link": link, "description": summary or content})

    return entries[:10]


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            return parse_rss_xml(text)
    except Exception as e:
        logger.error(f"Failed to fetch feed {url}: {e}")
        return []


def is_relevant(title: str, description: str, keywords: dict) -> bool:
    text = f"{title} {description}".lower()
    exclude = [kw.lower() for kw in keywords.get("exclude", [])]
    for kw in exclude:
        if kw in text:
            return False
    all_keywords = [kw.lower() for kw in keywords.get("primary", []) + keywords.get("secondary", [])]
    for kw in all_keywords:
        if kw in text:
            return True
    return False


def score_entry(title: str, description: str, keywords: dict) -> int:
    text = f"{title} {description}".lower()
    score = 0
    for kw in keywords.get("primary", []):
        if kw.lower() in text:
            score += 3
    for kw in keywords.get("secondary", []):
        if kw.lower() in text:
            score += 1
    return score


def is_duplicate(title: str, existing_titles: list, threshold: float = 0.8) -> bool:
    for existing in existing_titles:
        if levenshtein_ratio(title.lower(), existing.lower()) > threshold:
            return True
    return False


async def parse_all_feeds() -> list:
    sources = load_sources()
    keywords = load_keywords()
    results = []
    existing_titles = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_feed(session, src["url"]) for src in sources["rss"]]
        feeds = await asyncio.gather(*tasks)

        for src, entries in zip(sources["rss"], feeds):
            for entry in entries:
                title = entry.get("title", "").strip()
                description = entry.get("description", "").strip()
                link = entry.get("link", "")

                if not title or not link:
                    continue

                if not is_relevant(title, description, keywords):
                    continue

                if is_duplicate(title, existing_titles):
                    continue

                entry_score = score_entry(title, description, keywords)
                existing_titles.append(title)

                try:
                    summary = await generate_news_summary(title, description)
                except Exception as e:
                    logger.error(f"Failed to summarize {title}: {e}")
                    summary = description[:300]

                await save_news(
                    title=title,
                    url=link,
                    source=src["name"],
                    summary=summary,
                    score=entry_score,
                )
                results.append(
                    {"title": title, "url": link, "source": src["name"], "summary": summary, "score": entry_score}
                )

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Parsed {len(results)} relevant news items")
    return results[:5]
