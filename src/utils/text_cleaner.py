import re


def clean_markdown(text: str) -> str:
    """Remove markdown formatting, keep plain text with emojis and line breaks."""
    # Remove code blocks (``` ... ```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code (`...`)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # Remove headings (## ### #### etc.)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Remove bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Remove italic (*text* or _text_) — but not emoji patterns or arrows
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_\n]+?)_(?!\w)', r'\1', text)
    # Remove blockquotes (> at start of line)
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # Remove horizontal rules (--- or ***)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Remove image/link markdown ![alt](url) -> alt, [text](url) -> text
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Clean up double spaces
    text = re.sub(r'  +', ' ', text)
    # Clean up triple+ newlines to double
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
