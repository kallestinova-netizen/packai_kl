import io
import logging
import re
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

# Final output sizes
OUTPUT_SIZES = {
    "linkedin": (1200, 627),
    "telegram": (1280, 720),
    "threads": (1080, 1080),
    "stories": (1080, 1920),
}

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


def _extract_title(text: str) -> str:
    """Extract a short title from the post text (first meaningful line, max 80 chars)."""
    lines = text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) > 10:
            if len(stripped) > 80:
                return stripped[:77] + "..."
            return stripped
    return lines[0].strip()[:80] if lines else "PACK AI"


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels."""
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

    return lines[:5]  # Max 5 lines


def _overlay_branding(
    bg_image: Image.Image,
    title: str,
    image_format: str,
) -> Image.Image:
    """Apply brand overlay: PACK AI tag, title text, watermark."""
    brand = load_brand()
    output_size = OUTPUT_SIZES[image_format]

    # Resize background to target
    img = bg_image.resize(output_size, Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    width, height = output_size
    padding = 40

    # Color values
    accent_green = brand["colors"]["accent_green"]
    dark_text = brand["colors"]["dark_text"]

    # --- PACK AI tag (green pill, top-left) ---
    tag_font_size = max(20, int(height * 0.03))
    tag_font = _load_font("Manrope-Bold.ttf", tag_font_size)

    tag_text = "PACK AI"
    tag_bbox = tag_font.getbbox(tag_text)
    tag_w = tag_bbox[2] - tag_bbox[0] + 30
    tag_h = tag_bbox[3] - tag_bbox[1] + 16

    tag_x = padding
    tag_y = padding

    # Draw pill background
    draw.rounded_rectangle(
        [tag_x, tag_y, tag_x + tag_w, tag_y + tag_h],
        radius=tag_h // 2,
        fill=accent_green,
    )
    # Draw tag text
    draw.text(
        (tag_x + 15, tag_y + 8),
        tag_text,
        fill=dark_text,
        font=tag_font,
    )

    # --- Title text (center area) ---
    heading_sizes = brand["typography"]["heading"]["sizes"]
    size_key = {
        "linkedin": "linkedin_1200x627",
        "telegram": "telegram_1280x720",
        "threads": "instagram_1080x1080",
        "stories": "instagram_stories_1080x1920",
    }.get(image_format, "linkedin_1200x627")

    title_font_size = heading_sizes.get(size_key, 48)
    title_font = _load_font("Unbounded-Bold.ttf", title_font_size)

    max_text_width = width - padding * 2 - 40
    wrapped = _wrap_text(title, title_font, max_text_width)

    # Calculate text block height
    line_height = title_font_size + 8
    text_block_height = len(wrapped) * line_height

    # Position: vertically centered, slightly above middle
    text_y = (height - text_block_height) // 2 - int(height * 0.05)

    # Draw semi-transparent background behind text
    if wrapped:
        bg_rect_y1 = text_y - 20
        bg_rect_y2 = text_y + text_block_height + 20
        bg_rect_x1 = padding
        bg_rect_x2 = width - padding

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [bg_rect_x1, bg_rect_y1, bg_rect_x2, bg_rect_y2],
            radius=16,
            fill=(245, 245, 240, 200),  # warm white, semi-transparent
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(img)

    for i, line in enumerate(wrapped):
        y = text_y + i * line_height
        # Center horizontally
        line_bbox = title_font.getbbox(line)
        line_w = line_bbox[2] - line_bbox[0]
        x = (width - line_w) // 2
        draw.text((x, y), line, fill=dark_text, font=title_font)

    # --- Watermark: packai.io (bottom-right) ---
    watermark_font_size = max(16, int(height * 0.025))
    watermark_font = _load_font("Manrope-Regular.ttf", watermark_font_size)
    watermark_text = "packai.io"

    wm_bbox = watermark_font.getbbox(watermark_text)
    wm_w = wm_bbox[2] - wm_bbox[0]
    wm_x = width - padding - wm_w
    wm_y = height - padding - (wm_bbox[3] - wm_bbox[1])

    draw.text((wm_x, wm_y), watermark_text, fill=dark_text, font=watermark_font)

    # Convert back to RGB for saving
    if img.mode == "RGBA":
        final = Image.new("RGB", img.size, (245, 245, 240))
        final.paste(img, mask=img.split()[3])
        return final

    return img


async def _generate_background(topic: str, image_format: str) -> Image.Image:
    """Generate background image using DALL-E 3."""
    try:
        image_prompt_template = load_prompt("image_prompt.txt")
    except FileNotFoundError:
        image_prompt_template = (
            "Create a clean, minimalist background image for a social media post. "
            "Light warm tones (#F5F5F0 base), abstract geometric shapes, "
            "subtle green (#A8E847) accents. No text. Topic: {topic}"
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

    import base64
    image_data = base64.b64decode(response.data[0].b64_json)
    return Image.open(io.BytesIO(image_data))


async def generate_post_image(
    content_id: int,
    post_text: str,
    image_format: str = "linkedin",
    post_number: int = 0,
) -> str:
    """Generate a branded image for a post. Returns file path."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    title = _extract_title(post_text)
    logger.info(f"Generating image: format={image_format}, title={title[:40]}...")

    # Generate DALL-E background
    bg_image = await _generate_background(title, image_format)

    # Apply brand overlay
    final_image = _overlay_branding(bg_image, title, image_format)

    # Save
    date_str = datetime.now().strftime("%Y%m%d")
    post_num = post_number if post_number else content_id
    filename = f"{date_str}_{post_num}_{image_format}.png"
    filepath = IMAGES_DIR / filename

    final_image.save(str(filepath), "PNG", optimize=True)
    logger.info(f"Image saved: {filepath}")

    return str(filepath)
