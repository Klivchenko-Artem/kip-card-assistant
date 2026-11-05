from app.input_check import ParsedInput
from app.schemas import Commercial, CoreSpecs, LlmDraft, ProductInput, SpecChoice

PRODUCT = ProductInput(
    name="Манометр показывающий DM 02",
    manufacturer="Манотомь",
    specs={
        "диапазон измерений": "0–1,6 МПа",
        "класс точности": "1,5",
        "присоединение": "G1/2",
        "диаметр корпуса": "100 мм",
    },
    description="Прибор предназначен для измерения избыточного давления.",
)

GOOD_TEXT = (
    "Манометр показывающий DM 02 производства Манотомь измеряет избыточное давление "
    "в диапазоне 0–1,6 МПа, класс точности 1,5. "
) * 7


def make_draft(**changes) -> LlmDraft:
    data = dict(
        seo_title="Манометр показывающий DM 02 Манотомь, 0–1,6 МПа",
        seo_description=GOOD_TEXT,
        core_specs=CoreSpecs(range=["диапазон измерений"], accuracy=["класс точности"]),
        key_specs=[
            SpecChoice(label="Присоединение", source_key="присоединение"),
            SpecChoice(label="Материал корпуса", source_key=None),
        ],
        search_queries=["манометр dm 02", "манометр 1,6 мпа", "манометр манотомь"],
        commercial=Commercial(audience="Службы КИПиА.", tasks=["Контроль давления"]),
        clarifications=[],
    )
    data.update(changes)
    return LlmDraft(**data)


class FakeClient:
    """Отдает заранее заданные черновики и запоминает, что ему прислали."""

    def __init__(self, *drafts: LlmDraft):
        self.drafts = list(drafts)
        self.calls: list[list[dict]] = []

    def complete(self, messages):
        self.calls.append(messages)
        draft = self.drafts.pop(0)
        return draft, draft.model_dump_json()

    def close(self):
        pass


def parsed(missing=None) -> ParsedInput:
    return ParsedInput(product=PRODUCT, missing=missing or [])
