import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.llm import LlmBadOutput, LlmConfigError, LlmUnavailable
from tests.helpers import FakeClient, make_draft

BODY = json.dumps(
    {
        "name": "Манометр показывающий DM 02",
        "manufacturer": "Манотомь",
        "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5", "присоединение": "G1/2"},
        "description": "Прибор предназначен для измерения избыточного давления.",
    },
    ensure_ascii=False,
).encode()

api = TestClient(main.app)


def use_client(monkeypatch, client):
    monkeypatch.setattr(main, "make_client", lambda settings: client)


def test_page_opens():
    response = api.get("/")
    assert response.status_code == 200
    assert "Черновик карточки" in response.text


def test_card(monkeypatch):
    use_client(monkeypatch, FakeClient(make_draft()))
    response = api.post("/api/card", content=BODY)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ready", "needs_review")
    assert data["card"]["key_specs"][0]["value"] == "0–1,6 МПа"
    assert data["markdown"].startswith("## SEO-заголовок")


def test_broken_json():
    response = api.post("/api/card", content=b"{oops")
    assert response.status_code == 422
    assert "Некорректный JSON" in response.json()["error"]


def test_no_key(monkeypatch):
    def fail(settings):
        raise LlmConfigError("Не задан GROQ_API_KEY")

    monkeypatch.setattr(main, "make_client", fail)
    response = api.post("/api/card", content=BODY)
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["error"]


@pytest.mark.parametrize(
    "error, code", [(LlmUnavailable("лимит"), 503), (LlmBadOutput("не по схеме"), 502)]
)
def test_llm_errors(monkeypatch, error, code):
    class Failing:
        def complete(self, messages):
            raise error

        def close(self):
            pass

    use_client(monkeypatch, Failing())
    response = api.post("/api/card", content=BODY)
    assert response.status_code == code
    assert response.json() == {"error": str(error)}


def test_bad_setting_in_env(monkeypatch):
    monkeypatch.setenv("MAX_REWRITES", "много")
    response = api.post("/api/card", content=BODY)
    assert response.status_code == 503
    assert "MAX_REWRITES" in response.json()["error"]
