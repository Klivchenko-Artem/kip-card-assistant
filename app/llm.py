import json
import ssl
import time

import httpx
import truststore
from pydantic import ValidationError

from .config import Settings
from .schemas import LLM_JSON_SCHEMA, LlmDraft

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ATTEMPTS = 4
MAX_WAIT_SECONDS = 65
# Вся генерация карточки вместе с переписываниями не должна держать форму дольше
MAX_TOTAL_SECONDS = 240


class LlmError(Exception):
    """Текст ошибки показывается пользователю как есть."""


class LlmConfigError(LlmError):
    pass


class LlmUnavailable(LlmError):
    pass


class LlmBadOutput(LlmError):
    pass


def _wait_seconds(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        try:
            return float(response.headers.get("retry-after", ""))
        except ValueError:
            pass
    return float(2**attempt)


class GroqClient:
    def __init__(self, settings: Settings, transport=None, sleep=time.sleep):
        if not settings.api_key:
            raise LlmConfigError("Не задан GROQ_API_KEY: добавьте ключ в файл .env.")
        self.settings = settings
        self.sleep = sleep
        self.deadline = time.monotonic() + MAX_TOTAL_SECONDS
        self.http = httpx.Client(
            timeout=settings.timeout,
            transport=transport,
            # Системное хранилище сертификатов: иначе за антивирусом или корпоративным прокси TLS падает
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    def _body(self, messages: list[dict]) -> dict:
        return {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0.3,
            "max_completion_tokens": 2500,
            "reasoning_effort": "low",
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "card_draft", "strict": True, "schema": LLM_JSON_SCHEMA},
            },
        }

    def complete(self, messages: list[dict]) -> tuple[LlmDraft, str]:
        """Возвращает разобранный черновик и сырой JSON для следующего шага диалога."""
        last_error: LlmError = LlmUnavailable("Сервис модели не ответил.")
        if time.monotonic() >= self.deadline:
            raise LlmUnavailable("Вышло время на подготовку карточки.")
        for attempt in range(MAX_ATTEMPTS):
            response = None
            try:
                response = self.http.post(GROQ_URL, json=self._body(messages))
            except httpx.TimeoutException:
                last_error = LlmUnavailable("Сервис модели не ответил вовремя.")
            except httpx.HTTPError:
                last_error = LlmUnavailable("Не удалось подключиться к сервису модели.")
            else:
                if response.status_code in (401, 403):
                    raise LlmConfigError("Сервис модели отклонил ключ: проверьте GROQ_API_KEY.")
                if response.status_code == 429:
                    last_error = LlmUnavailable("Превышен лимит запросов к модели, повторите позже.")
                elif response.status_code == 413:
                    raise LlmUnavailable("Данные о товаре слишком большие для лимита модели, сократите их.")
                elif response.status_code >= 500:
                    last_error = LlmUnavailable("Сервис модели временно недоступен.")
                elif response.status_code == 400 and "json_validate_failed" in response.text:
                    last_error = LlmBadOutput("Модель вернула ответ не по схеме.")
                elif response.status_code >= 400:
                    raise LlmUnavailable(f"Сервис модели вернул ошибку {response.status_code}.")
                else:
                    try:
                        return self._parse(response)
                    except LlmBadOutput as exc:
                        last_error = exc
            wait = _wait_seconds(response, attempt)
            out_of_time = time.monotonic() + wait + self.settings.timeout > self.deadline
            if attempt + 1 == MAX_ATTEMPTS or wait > MAX_WAIT_SECONDS or out_of_time:
                break
            self.sleep(wait)
        raise last_error

    def close(self) -> None:
        self.http.close()

    @staticmethod
    def _parse(response: httpx.Response) -> tuple[LlmDraft, str]:
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return LlmDraft.model_validate(json.loads(content)), content
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise LlmBadOutput("Модель вернула ответ не по схеме.") from None
