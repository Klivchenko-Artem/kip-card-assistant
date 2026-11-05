import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    timeout: float
    max_rewrites: int


class ConfigError(Exception):
    """Текст ошибки показывается пользователю как есть."""


def _number(name: str, default: str, kind):
    raw = os.getenv(name, "").strip() or default
    try:
        return kind(raw)
    except ValueError:
        raise ConfigError(f"В .env неверное значение {name}: нужно число.") from None


def load_settings() -> Settings:
    return Settings(
        api_key=os.getenv("GROQ_API_KEY", "").strip(),
        model=os.getenv("GROQ_MODEL", "").strip() or "openai/gpt-oss-120b",
        timeout=_number("LLM_TIMEOUT_SECONDS", "60", float),
        max_rewrites=_number("MAX_REWRITES", "2", int),
    )
