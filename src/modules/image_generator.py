import os
import json
import logging
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

KIE_API_URL = "https://api.kie.ai/api/v1/nano-banana"
KIE_PRO_URL = "https://api.kie.ai/api/v1/nano-banana-pro"

FORMATS = {
    "linkedin": {"aspect": "16:9", "resolution": "1K"},
    "telegram": {"aspect": "16:9", "resolution": "1K"},
    "threads": {"aspect": "1:1", "resolution": "1K"},
    "stories": {"aspect": "9:16", "resolution": "1K"},
}


async def generate_post_image(
    post_text: str,
    format_name: str = "telegram",
    photo_url: str = None,
    *,
    content_id: int = 0,
    image_format: str = None,
) -> str:
    """Generate a branded image via Kie.ai Nano Banana. Returns file path or None."""
    # Support legacy kwarg image_format -> format_name
    if image_format and format_name == "telegram":
        format_name = image_format

    api_key = os.getenv("KIE_API_KEY")
    if not api_key:
        logger.error("KIE_API_KEY not set")
        return None

    # Extract short title (5-6 words)
    title = " ".join(post_text.split("\n")[0].split()[:6])

    fmt = FORMATS.get(format_name, FORMATS["telegram"])

    prompt = (
        f"Create a minimalist social media post image.\n"
        f"Background: warm beige color #F5F5F0\n"
        f"Accent elements: bright lime green #A8E847 geometric shapes (circles, lines)\n"
        f"Bold text on image: '{title}' in dark color #1A1A1A, modern sans-serif font\n"
        f"Small green tag 'PACK AI' with lime background in top left corner\n"
        f"Small text 'packai.io' in bottom right corner\n"
        f"Style: ultra clean, minimal, lots of white space, Apple-style design\n"
        f"Aspect ratio: {fmt['aspect']}\n"
        f"NO photographs of people. Abstract geometric accents only."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # If photo provided, use Nano Banana Edit to insert into branded layout
    if photo_url:
        payload = {
            "prompt": (
                f"Insert this photo into a branded social media layout. "
                f"Background: beige #F5F5F0. Lime green #A8E847 frame around photo. "
                f"Text '{title}' in bold dark font below. "
                f"Tag 'PACK AI' top left. 'packai.io' bottom right. Clean minimal design."
            ),
            "image_urls": [photo_url],
            "output_format": "png",
            "image_size": fmt["aspect"],
        }
        url = KIE_API_URL.replace("nano-banana", "nano-banana/edit")
    else:
        payload = {
            "prompt": prompt,
            "output_format": "png",
            "image_size": fmt["aspect"],
        }
        url = KIE_API_URL

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"Kie.ai error {resp.status}: {error[:200]}")
                    return None

                data = await resp.json()
                image_url = None

                # Parse response - Kie.ai returns image URL
                if isinstance(data, dict):
                    image_url = (
                        data.get("image_url")
                        or data.get("url")
                        or data.get("output", {}).get("url")
                    )
                    if not image_url and "images" in data:
                        images = data["images"]
                        if images and isinstance(images, list):
                            image_url = images[0].get("url")

                if not image_url:
                    logger.error(f"No image URL in response: {str(data)[:200]}")
                    return None

                # Download image
                async with session.get(image_url) as img_resp:
                    if img_resp.status == 200:
                        img_data = await img_resp.read()
                        os.makedirs("data/images", exist_ok=True)
                        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{format_name}.png"
                        filepath = f"data/images/{filename}"
                        with open(filepath, "wb") as f:
                            f.write(img_data)
                        logger.info(f"Image saved: {filepath}")
                        return filepath

                return None
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return None
