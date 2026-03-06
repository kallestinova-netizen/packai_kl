import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI
from PIL import Image, ImageDraw, ImageFont

from src.config import OPENAI_API_KEY, load_brand, load_prompt, BASE_DIR

logger = logging.getLogger(__name__)

IMAGES_DIR = BASE_DIR / "data" / "images"
FONTS_DIR = BASE_DIR / "assets" / "fonts"

# DALL-E 3 size mapping per image format
DALLE_SIZES = {
    "linkedin": "1792x1024",   # landscape
    "telegram": "1792x1024",   # landscape
    "threads": "1024x1024",    # square
    "stories": "1024x1792",    # portrait
}

# Format specs: output size + title max chars
FORMATS = {
    "linkedin": {"width": 1200, "height": 627, "title_max_chars": 60},
    "telegram": {"width": 1280, "height": 720, "title_max_chars": 50},
    "threads": {"width": 1080, "height": 1080, "title_max_chars": 45},
    "stories": {"width": 1080, "height": 1920, "title_max_chars": 40},
}

PADDING = 60

_client = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


def _load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font from assets/fonts/, fallback to default."""
    font_path = FONTS_DIR / font_name
    try:
        return ImageFont.truetype(str(font_path), size)
    except (OSError, IOError):
        logger.warning(f"Font {font_name} not found at {font_path}, using default")
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _extract_title(text: str, max_chars: int = 60) -> str:
    """Extract a short title from the post text (first meaningful line)."""
    lines = text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) > 10:
            if len(stripped) > max_chars:
                # Cut at last space within limit
                cut = stripped[:max_chars].rsplit(" ", 1)[0]
                return cut if len(cut) > 10 else stripped[:max_chars - 3] + "..."
            return stripped
    return lines[0].strip()[:max_chars] if lines else "PACK AI"


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels. Max 3 lines."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        text_width = bbox[2] - bbox[0]
        if text_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines[:3]  # Max 3 lines per spec


def _overlay_branding(
    bg_image: Image.Image,
    title: str,
    image_format: str,
) -> Image.Image:
    """Apply brand overlay: PACK AI tag, title text, watermark."""
    brand = load_brand()
    fmt = FORMATS[image_format]
    width, height = fmt["width"], fmt["height"]

    # Resize background to target
    img = bg_image.resize((width, height), Image.LANCZOS).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Color values
    accent_green = brand["colors"]["accent_green"]
    dark_text = brand["colors"]["dark_text"]

    # --- PACK AI tag (green pill, top-left) ---
    tag_font = _load_font("Manrope-Bold.ttf", 20)
    tag_text = "PACK AI"
    tag_bbox = tag_font.getbbox(tag_text)
    tag_w = tag_bbox[2] - tag_bbox[0] + 32
    tag_h = tag_bbox[3] - tag_bbox[1] + 16
    tag_x, tag_y = PADDING, PADDING

    draw.rounded_rectangle(
        [tag_x, tag_y, tag_x + tag_w, tag_y + tag_h],
        radius=20,
        fill=accent_green,
    )
    draw.text(
        (tag_x + 16, tag_y + 8),
        tag_text,
        fill=dark_text,
        font=tag_font,
    )

    # --- Title text (bottom third) ---
    heading_sizes = brand["typography"]["heading"]["sizes"]
    size_key = {
        "linkedin": "linkedin_1200x627",
        "telegram": "telegram_1280x720",
        "threads": "instagram_1080x1080",
        "stories": "instagram_stories_1080x1920",
    }.get(image_format, "linkedin_1200x627")

    title_font_size = heading_sizes.get(size_key, 48)
    title_font = _load_font("Unbounded-Bold.ttf", title_font_size)

    max_text_width = width - PADDING * 2
    wrapped = _wrap_text(title, title_font, max_text_width)

    # Line height = font_size * 1.3
    line_height = int(title_font_size * 1.3)
    text_block_height = len(wrapped) * line_height

    # Position: bottom third, with padding from bottom
    y_start = height - text_block_height - PADDING - 20

    # Semi-transparent background behind title for readability
    if wrapped:
        bg_rect_y1 = y_start - 20
        bg_rect_y2 = y_start + text_block_height + 20
        bg_rect_x1 = PADDING - 20
        bg_rect_x2 = width - PADDING + 20

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [bg_rect_x1, bg_rect_y1, bg_rect_x2, bg_rect_y2],
            radius=16,
            fill=(245, 245, 240, 200),
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

    for i, line in enumerate(wrapped):
        y = y_start + i * line_height
        draw.text((PADDING, y), line, fill=dark_text, font=title_font)

    # --- Watermark: packai.io (bottom-right, 40% opacity) ---
    watermark_font = _load_font("Manrope-Regular.ttf", 16)
    watermark_text = "packai.io"

    wm_bbox = watermark_font.getbbox(watermark_text)
    wm_w = wm_bbox[2] - wm_bbox[0]
    wm_h = wm_bbox[3] - wm_bbox[1]
    wm_x = width - PADDING - wm_w
    wm_y = height - PADDING

    # 40% opacity: alpha = 102 out of 255
    draw.text((wm_x, wm_y), watermark_text, fill=(26, 26, 26, 102), font=watermark_font)

    # Convert to RGB for PNG saving
    final = Image.new("RGB", img.size, (245, 245, 240))
    final.paste(img, mask=img.split()[3])
    return final


async def _generate_background(topic: str, image_format: str) -> Image.Image:
    """Generate background image using DALL-E 3."""
    try:
        image_prompt_template = load_prompt("image_prompt.txt")
    except FileNotFoundError:
        image_prompt_template = (
            "Создай фоновое изображение для поста в социальных сетях. "
            "Минималистичный стиль, тёплый светлый фон, лаймово-зелёные акценты. "
            "БЕЗ текста. Тема: {topic}"
        )

    prompt = image_prompt_template.replace("{topic}", topic[:200])
    dalle_size = DALLE_SIZES.get(image_format, "1792x1024")

    response = await _get_client().images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=dalle_size,
        quality="standard",
        n=1,
        response_format="b64_json",
    )

    image_data = base64.b64decode(response.data[0].b64_json)
    return Image.open(io.BytesIO(image_data))


async def generate_post_image(
    content_id: int,
    post_text: str,
    image_format: str = "telegram",
    post_number: int = 0,
) -> str:
    """Generate a branded image for a post. Returns file path."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    fmt = FORMATS.get(image_format, FORMATS["telegram"])
    title = _extract_title(post_text, max_chars=fmt["title_max_chars"])
    logger.info(f"Generating image: format={image_format}, title={title[:40]}...")

    # Generate DALL-E background
    bg_image = await _generate_background(title, image_format)

    # Apply brand overlay
    final_image = _overlay_branding(bg_image, title, image_format)

    # Save with naming: {date}_{post_number}_{format}.png
    date_str = datetime.now().strftime("%Y-%m-%d")
    post_num = f"{post_number:02d}" if post_number else f"{content_id:02d}"
    filename = f"{date_str}_{post_num}_{image_format}.png"
    filepath = IMAGES_DIR / filename

    final_image.save(str(filepath), "PNG", optimize=True)
    logger.info(f"Image saved: {filepath}")

    return str(filepath)
