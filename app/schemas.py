from pydantic import BaseModel, Field

NO_DATA = "данных нет"

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5

# Параметры, которые есть в задании и которые покупатель ищет первыми.
# Строка в карточке будет всегда, даже если значения нет.
CORE_SPECS = {
    "range": "Диапазон измерений",
    "accuracy": "Точность",
    "power": "Питание",
    "housing": "Тип корпуса",
    "interfaces": "Интерфейсы",
}


class ProductInput(BaseModel):
    name: str
    manufacturer: str = ""
    specs: dict[str, str] = Field(default_factory=dict)
    description: str = ""


class SpecChoice(BaseModel):
    """Ответ модели: подпись и ключ из входных specs. Значение модель не пишет."""

    label: str
    source_key: str | None


class CoreSpecs(BaseModel):
    """Ключи из входных specs для обязательных параметров, пустой список значит данных нет."""

    range: list[str] = Field(default_factory=list)
    accuracy: list[str] = Field(default_factory=list)
    power: list[str] = Field(default_factory=list)
    housing: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)


class Commercial(BaseModel):
    audience: str
    tasks: list[str]


class LlmDraft(BaseModel):
    seo_title: str
    seo_description: str
    core_specs: CoreSpecs
    key_specs: list[SpecChoice]
    search_queries: list[str]
    commercial: Commercial
    clarifications: list[str]


class KeySpec(BaseModel):
    name: str
    value: str


class Card(BaseModel):
    seo_title: str
    seo_description: str
    key_specs: list[KeySpec]
    search_queries: list[str]
    commercial: Commercial


class CardResult(BaseModel):
    status: str  # ready или needs_review
    card: Card
    missing_data: list[str]
    warnings: list[str]
    rewrites: int
    markdown: str = ""


# Схема для structured outputs. В строгом режиме обязательны все поля
# и additionalProperties: false, ограничения длины проверяет код.
LLM_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "seo_title",
        "seo_description",
        "core_specs",
        "key_specs",
        "search_queries",
        "commercial",
        "clarifications",
    ],
    "properties": {
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "core_specs": {
            "type": "object",
            "additionalProperties": False,
            "required": list(CORE_SPECS),
            "properties": {
                name: {"type": "array", "items": {"type": "string"}} for name in CORE_SPECS
            },
        },
        "key_specs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "source_key"],
                "properties": {
                    "label": {"type": "string"},
                    "source_key": {"type": ["string", "null"]},
                },
            },
        },
        "search_queries": {"type": "array", "items": {"type": "string"}},
        "commercial": {
            "type": "object",
            "additionalProperties": False,
            "required": ["audience", "tasks"],
            "properties": {
                "audience": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "clarifications": {"type": "array", "items": {"type": "string"}},
    },
}
