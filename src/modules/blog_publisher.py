import os
import io
import json
import ftplib
import asyncio
import logging
from datetime import date

import anthropic

from src.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

FTP_HOST = os.getenv("FTP_HOST", "kallestinova.ru")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASSWORD = os.getenv("FTP_PASSWORD", "")
FTP_BLOG_PATH = "/kallestinova.ru/public_html/blog"


async def generate_blog_article(source_text: str) -> dict | None:
    """Generate a blog article via Claude API. Returns dict or None on error."""
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    system_prompt = (
        "Ты — Натали Каллестинова, эксперт по AI-автоматизации для бизнеса. "
        "Стиль: прямой, экспертный, с конкретными цифрами и фактами. Без воды.\n\n"
        "ПРАВИЛА НАПИСАНИЯ СТАТЬИ:\n"
        "1. Первый абзац — прямой ответ на тему БЕЗ вступлений типа 'в современном мире'. "
        "AI-системы извлекают первые 200 слов — они должны быть максимально информативными.\n"
        "2. Короткие абзацы: максимум 2-3 предложения. Это повышает extractability для RAG-систем.\n"
        "3. Минимум 3 конкретные цифры или факта с источниками. AI цитирует контент с данными в 2-4 раза чаще.\n"
        "4. Подзаголовки H2 формулируй как вопросы: 'Как...', 'Почему...', 'Что такое...' — "
        "они совпадают с запросами пользователей к AI.\n"
        "5. В конце добавь 2-3 FAQ вопроса с ответами строго до 40 слов каждый.\n\n"
        "ФОРМАТ ОТВЕТА — строго JSON без markdown-обёртки:\n"
        "{\n"
        '  "slug": "url-slug-na-angliyskom",\n'
        '  "title": "Заголовок статьи на русском",\n'
        '  "excerpt": "Краткое описание 1-2 предложения",\n'
        '  "tag": "Категория (AI, Маркетинг, Автоматизация, Контент)",\n'
        '  "meta_description": "SEO описание до 160 символов",\n'
        '  "keywords": "ключевые, слова, через, запятую",\n'
        '  "read_time": "5",\n'
        '  "body_html": "<p>HTML-текст статьи с тегами p, h2, h3, blockquote, strong, ul, ol, li</p>",\n'
        '  "faq": [\n'
        '    {"question": "Вопрос?", "answer": "Ответ до 40 слов."},\n'
        '    {"question": "Вопрос?", "answer": "Ответ до 40 слов."}\n'
        "  ]\n"
        "}"
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Напиши статью для блога на тему:\n\n{source_text}"}
            ],
        )

        raw = response.content[0].text.strip()

        # Strip ```json wrapper if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        article = json.loads(raw)

        # Validate required fields
        required = ["slug", "title", "body_html"]
        for field in required:
            if not article.get(field):
                logger.error(f"Missing required field: {field}")
                return None

        # Defaults
        article.setdefault("excerpt", "")
        article.setdefault("tag", "AI")
        article.setdefault("meta_description", article["excerpt"])
        article.setdefault("keywords", "")
        article.setdefault("read_time", "5")
        article.setdefault("faq", [])

        return article

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Blog article generation failed: {e}")
        return None


def build_article_html(article: dict) -> str:
    """Build a complete standalone HTML page for the article."""
    today = date.today().isoformat()
    slug = article.get("slug", "article")
    title = article.get("title", "")
    excerpt = article.get("excerpt", "")
    meta_desc = article.get("meta_description", excerpt)
    keywords = article.get("keywords", "")
    tag = article.get("tag", "AI")
    read_time = article.get("read_time", "5")
    body_html = article.get("body_html", "")
    faq = article.get("faq", [])
    canonical = f"https://kallestinova.ru/blog/{slug}.html"

    # Article Schema JSON-LD
    article_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": meta_desc,
        "datePublished": today,
        "dateModified": today,
        "author": {
            "@type": "Person",
            "name": "Натали Каллестинова",
            "url": "https://kallestinova.ru"
        },
        "publisher": {
            "@type": "Organization",
            "name": "KALLESTINOVA.RU",
            "url": "https://kallestinova.ru"
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical
        },
        "keywords": keywords,
        "articleSection": tag
    }, ensure_ascii=False)

    # FAQPage Schema JSON-LD
    faq_schema = ""
    if faq:
        faq_entries = []
        for item in faq[:3]:
            faq_entries.append({
                "@type": "Question",
                "name": item.get("question", ""),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item.get("answer", "")
                }
            })
        faq_schema_obj = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": faq_entries
        }
        faq_schema = f'<script type="application/ld+json">{json.dumps(faq_schema_obj, ensure_ascii=False)}</script>'

    # FAQ HTML section
    faq_html = ""
    if faq:
        faq_items = ""
        for item in faq[:3]:
            q = item.get("question", "")
            a = item.get("answer", "")
            faq_items += f"<dt>{q}</dt><dd>{a}</dd>"
        faq_html = f'<section class="faq"><h2>Частые вопросы</h2><dl>{faq_items}</dl></section>'

    # Escape title for HTML attributes
    title_attr = title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
    meta_desc_attr = meta_desc.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_attr} — KALLESTINOVA.RU</title>
<meta name="description" content="{meta_desc_attr}">
<meta name="keywords" content="{keywords}">
<meta name="date" content="{today}">
<meta name="speakable" content="true">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title_attr}">
<meta property="og:description" content="{meta_desc_attr}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="KALLESTINOVA.RU">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_attr}">
<meta name="twitter:description" content="{meta_desc_attr}">
<script type="application/ld+json">{article_schema}</script>
{faq_schema}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@700;800;900&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --lime: #A8E847;
  --lime-d: #3D7A00;
  --lime-bg: #EEF9D0;
  --lime-bg2: #F5FCDF;
  --bg: #FAFAF7;
  --ink: #1A1A1A;
  --gray: #6B7280;
  --gray-l: #9CA3AF;
  --gray-ll: #D1D5DB;
  --r-xl: 40px;
  --r-lg: 28px;
  --r-md: 20px;
  --r-pill: 100px;
}}
*,*::before,*::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Manrope', sans-serif; background: var(--bg); color: var(--ink); line-height: 1.6; }}
.nav {{ display: flex; justify-content: space-between; align-items: center; max-width: 960px; margin: 0 auto; padding: 24px 20px; }}
.nav-logo {{ font-family: 'Unbounded', sans-serif; font-weight: 900; font-size: 18px; color: var(--ink); text-decoration: none; }}
.nav-back {{ font-family: 'Manrope', sans-serif; font-size: 14px; color: var(--gray); text-decoration: none; transition: color .2s; }}
.nav-back:hover {{ color: var(--ink); }}
article {{ max-width: 720px; margin: 0 auto; padding: 0 20px 60px; }}
.article-tag {{ display: inline-block; font-family: 'Unbounded', sans-serif; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; background: var(--lime-bg); color: var(--lime-d); padding: 6px 16px; border-radius: var(--r-pill); margin-bottom: 20px; }}
.article-title {{ font-family: 'Unbounded', sans-serif; font-size: clamp(24px, 5vw, 40px); font-weight: 900; line-height: 1.2; color: var(--ink); margin-bottom: 16px; }}
.article-meta {{ font-size: 13px; color: var(--gray-l); margin-bottom: 40px; }}
.article-body p {{ font-size: 16px; line-height: 1.85; color: var(--gray); margin-bottom: 20px; }}
.article-body p:first-child {{ font-size: 18px; color: var(--ink); font-weight: 500; }}
.article-body h2 {{ font-family: 'Unbounded', sans-serif; font-size: 22px; font-weight: 900; color: var(--ink); margin: 40px 0 16px; }}
.article-body h3 {{ font-family: 'Unbounded', sans-serif; font-size: 17px; font-weight: 800; color: var(--ink); margin: 32px 0 12px; }}
.article-body blockquote {{ border-left: 3px solid var(--lime); background: var(--lime-bg2); padding: 16px 20px; margin: 24px 0; border-radius: 0 var(--r-md) var(--r-md) 0; }}
.article-body blockquote p {{ color: var(--ink); margin-bottom: 0; }}
.article-body strong {{ color: var(--ink); font-weight: 700; }}
.article-body ul, .article-body ol {{ padding-left: 24px; margin-bottom: 20px; color: var(--gray); }}
.article-body li {{ margin-bottom: 8px; line-height: 1.7; }}
.faq {{ margin-top: 48px; padding-top: 32px; border-top: 1px solid var(--gray-ll); }}
.faq h2 {{ font-family: 'Unbounded', sans-serif; font-size: 22px; font-weight: 900; color: var(--ink); margin-bottom: 24px; }}
.faq dl {{ display: grid; gap: 16px; }}
.faq dt {{ font-weight: 700; color: var(--ink); font-size: 16px; }}
.faq dd {{ color: var(--gray); font-size: 15px; line-height: 1.7; margin-left: 0; padding-bottom: 16px; border-bottom: 1px solid var(--gray-ll); }}
.cta {{ max-width: 720px; margin: 40px auto; padding: 40px; background: var(--lime-bg); border-radius: var(--r-xl); text-align: center; }}
.cta h3 {{ font-family: 'Unbounded', sans-serif; font-size: 20px; font-weight: 900; margin-bottom: 16px; }}
.cta-btn {{ display: inline-block; font-family: 'Manrope', sans-serif; font-weight: 700; font-size: 15px; background: var(--lime); color: var(--ink); padding: 14px 32px; border-radius: var(--r-pill); text-decoration: none; transition: background .2s; }}
.cta-btn:hover {{ background: #9AD83D; }}
footer {{ text-align: center; padding: 40px 20px; font-size: 13px; color: var(--gray-l); }}
footer span {{ font-family: 'Unbounded', sans-serif; font-weight: 700; }}
</style>
</head>
<body>
<nav class="nav">
  <a href="/" class="nav-logo">KALLESTINOVA.RU</a>
  <a href="/" class="nav-back">&larr; Назад на сайт</a>
</nav>
<article>
  <span class="article-tag">{tag}</span>
  <h1 class="article-title">{title}</h1>
  <div class="article-meta">{today} &middot; {read_time} мин чтения</div>
  <div class="article-body">
    {body_html}
  </div>
  {faq_html}
</article>
<div class="cta">
  <h3>Хотите внедрить ИИ-агентов?</h3>
  <p style="color:var(--gray);margin-bottom:24px;">Разберу ваш бизнес и покажу, где AI даст максимальный ROI</p>
  <a href="/#contact" class="cta-btn">Получить бесплатный анализ</a>
</div>
<footer>
  <span>KALLESTINOVA.RU</span><br>&copy; 2026
</footer>
</body>
</html>"""
    return html


def _ftp_upload(html_content: str, article: dict) -> str | None:
    """Synchronous FTP upload. Returns article URL or None."""
    if not FTP_USER or not FTP_PASSWORD:
        logger.error("FTP credentials not configured (FTP_USER or FTP_PASSWORD empty)")
        return None

    slug = article.get("slug", "article")
    filename = f"{slug}.html"
    today = date.today().isoformat()

    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASSWORD)
        ftp.cwd(FTP_BLOG_PATH)

        # Upload HTML file
        html_bytes = html_content.encode("utf-8")
        ftp.storbinary(f"STOR {filename}", io.BytesIO(html_bytes))
        logger.info(f"Uploaded {filename} to {FTP_BLOG_PATH}")

        # Download current articles.json
        articles = []
        try:
            buf = io.BytesIO()
            ftp.retrbinary("RETR articles.json", buf.write)
            buf.seek(0)
            articles = json.loads(buf.read().decode("utf-8"))
        except ftplib.error_perm:
            logger.warning("articles.json not found on server, creating new one")

        # Add new entry at the beginning
        new_entry = {
            "slug": slug,
            "title": article.get("title", ""),
            "excerpt": article.get("excerpt", ""),
            "tag": article.get("tag", "AI"),
            "date": today,
            "keywords": article.get("keywords", ""),
        }
        articles.insert(0, new_entry)

        # Upload updated articles.json
        json_bytes = json.dumps(articles, ensure_ascii=False, indent=2).encode("utf-8")
        ftp.storbinary("STOR articles.json", io.BytesIO(json_bytes))
        logger.info("Updated articles.json")

        ftp.quit()

        url = f"https://kallestinova.ru/blog/{filename}"
        return url

    except Exception as e:
        logger.error(f"FTP upload failed: {e}")
        return None


async def publish_to_blog(article: dict) -> str | None:
    """Build HTML and publish via FTP. Returns URL or None on error."""
    try:
        html_content = build_article_html(article)
        url = await asyncio.to_thread(_ftp_upload, html_content, article)
        return url
    except Exception as e:
        logger.error(f"publish_to_blog failed: {e}")
        return None
