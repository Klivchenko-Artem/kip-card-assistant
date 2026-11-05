from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from .config import ConfigError, load_settings
from .generator import generate_card
from .input_check import InputError, parse_input
from .llm import GroqClient, LlmBadOutput, LlmError

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Черновики карточек КИП")


def make_client(settings):
    return GroqClient(settings)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/card")
async def create_card(request: Request):
    # Тело читаю сам: на кривой JSON нужен понятный ответ, а не стандартная ошибка 422
    raw = await request.body()
    try:
        parsed = parse_input(raw)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    client = None
    try:
        settings = load_settings()
        client = make_client(settings)
        result = await run_in_threadpool(generate_card, parsed, client, settings.max_rewrites)
    except LlmBadOutput as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    except (LlmError, ConfigError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    finally:
        if client is not None:
            client.close()
    return result.model_dump()


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return JSONResponse({"error": "Внутренняя ошибка сервиса."}, status_code=500)
