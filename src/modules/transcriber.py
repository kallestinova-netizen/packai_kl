import logging
import tempfile
from pathlib import Path

from openai import AsyncOpenAI
from src.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def transcribe_voice(file_bytes: bytes, file_name: str = "voice.ogg") -> str:
    suffix = Path(file_name).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.seek(0)

        client = _get_client()
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=open(tmp.name, "rb"),
            language="ru",
        )

    logger.info(f"Transcribed voice message: {transcript.text[:100]}...")
    return transcript.text
