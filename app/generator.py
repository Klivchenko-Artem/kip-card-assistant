import re

from .checks import check_draft, check_format, is_thin
from .input_check import ParsedInput
from .llm import GroqClient, LlmError
from .prompts import SYSTEM_PROMPT, rewrite_message, user_message
from .render import to_markdown
from .schemas import (
    CORE_SPECS,
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    NO_DATA,
    Card,
    CardResult,
    Commercial,
    KeySpec,
    LlmDraft,
    ProductInput,
)

# Эти подписи модель иногда добавляет с null, хотя все ясно из названия
USELESS_LABELS = {"тип прибора", "назначение", "название", "производитель", "модель"}

# Пустое поле из входа с таким именем уже показано обязательной строкой
CORE_SYNONYMS = {
    "диапазон измерений": "Диапазон измерений",
    "диапазон измерения": "Диапазон измерений",
    "класс точности": "Точность",
    "погрешность": "Точность",
    "питание": "Питание",
    "напряжение питания": "Питание",
    "тип корпуса": "Тип корпуса",
    "корпус": "Тип корпуса",
    "интерфейс": "Интерфейсы",
    "интерфейсы": "Интерфейсы",
}

THIN_WARNING = "Исходных данных мало, поэтому описание может быть короче 800 символов: дополните данные"

KEEP_DASH_AFTER = {"от", "до", "при", "около", "минус"}
SENTENCE_END = re.compile(r"(?<=[.!?\u2026])(\s+)(?=[А-ЯЁA-Z«])")


def _dash(match: re.Match) -> str:
    before, word, right = match.group(1), match.group(2), match.group(3)
    number_follows = right.isdigit() or right in "+-\u2212\u2013"
    is_range = word[-1].isdigit() or word.lower() in KEEP_DASH_AFTER
    # «10 мбар - 20 мбар»: слева значение с единицей, справа число
    if is_range or (before and number_follows):
        return match.group(0)
    return f"{before or ''}{word}: {right}"


def clean_text(text: str) -> str:
    """Неразрывные дефисы и тире-знаки препинания от модели мешают при вставке в CMS.
    Тире в диапазонах и перед отрицательными числами остается."""
    text = text.replace("\u2011", "-").replace("\u00a0", " ")
    return re.sub(r"(\d\S*[ \t]+)?(\S+)[ \t]+[\u2013\u2014][ \t]+(\S)", _dash, text).strip()


def fit_description(text: str) -> str:
    """Модель плохо считает символы: небольшой перелет убираю по целым предложениям.
    Граница это знак конца и заглавная буква, поэтому «1.5» и «защит. крышкой» не режутся."""
    parts = SENTENCE_END.split(text)
    while len(text) > DESCRIPTION_MAX and len(parts) >= 3:
        shorter = "".join(parts[:-2])
        if len(shorter) < DESCRIPTION_MIN:
            break
        parts = parts[:-2]
        text = shorter
    return text


def tidy(draft: LlmDraft) -> LlmDraft:
    return draft.model_copy(
        update={
            "seo_title": clean_text(draft.seo_title),
            "seo_description": fit_description(clean_text(draft.seo_description)),
            "search_queries": [clean_text(query) for query in draft.search_queries],
            "commercial": Commercial(
                audience=clean_text(draft.commercial.audience),
                tasks=[clean_text(task) for task in draft.commercial.tasks],
            ),
        }
    )


def core_value(keys: list[str], product: ProductInput) -> str | None:
    if not keys:
        return None
    if len(keys) == 1:
        return product.specs[keys[0]]
    return "; ".join(f"{key}: {product.specs[key]}" for key in keys)


def build_specs(draft: LlmDraft, product: ProductInput) -> list[KeySpec]:
    """Значение и его подпись берутся из входных данных, модель выбирает только ключ.
    Своя подпись модели остается лишь у строк без значения."""
    specs: list[KeySpec] = []
    rows: dict[str, KeySpec] = {}
    used_keys = set()

    def add(name: str, value: str | None) -> None:
        row = KeySpec(name=name, value=value or NO_DATA)
        specs.append(row)
        rows[name.lower()] = row

    for field, label in CORE_SPECS.items():
        keys = list(dict.fromkeys(k for k in getattr(draft.core_specs, field) if k in product.specs))
        used_keys.update(keys)
        add(label, core_value(keys, product))

    for item in draft.key_specs:
        label = item.label.strip()
        key = item.source_key
        if key in used_keys:
            continue
        if key in product.specs:
            used_keys.add(key)
            row = rows.get(key.lower())
            if row is not None and row.value == NO_DATA:
                row.value = product.specs[key]
            else:
                add(key[:1].upper() + key[1:], product.specs[key])
        elif label and label.lower() not in rows and label.lower() not in USELESS_LABELS:
            add(label, None)
    return specs


def empty_rows(empty_specs: list[str], specs: list[KeySpec]) -> list[KeySpec]:
    """Пустые поля из входа, кроме тех, что уже показаны строкой с тем же смыслом."""
    shown = {spec.name.lower() for spec in specs}
    return [
        KeySpec(name=key, value=NO_DATA)
        for key in empty_specs
        if key.lower() not in shown and key.lower() not in CORE_SYNONYMS
    ]


def unique_queries(queries: list[str]) -> list[str]:
    unique = {query.strip().lower(): query.strip() for query in reversed(queries) if query.strip()}
    return list(reversed(unique.values()))


def generate_card(parsed: ParsedInput, client: GroqClient, max_rewrites: int) -> CardResult:
    product = parsed.product
    thin = is_thin(product)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message(product, parsed.empty_specs, thin)},
    ]

    best: tuple[tuple[int, int], LlmDraft, list[str]] | None = None
    rewrites = 0
    while True:
        try:
            draft, raw = client.complete(messages)
        except LlmError:
            # Черновик уже есть: лучше отдать его с замечаниями, чем потерять из-за лимита
            if best is None:
                raise
            break
        draft = tidy(draft)
        issues = check_draft(draft, product)
        # Нарушенный формат хуже спорного слова: пустое описание не должно вытеснить текст
        rank = (len(check_format(draft, thin)), len(issues))
        if best is None or rank <= best[0]:
            best = (rank, draft, issues)
        if not issues or rewrites >= max_rewrites:
            break
        rewrites += 1
        messages = messages[:2] + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": rewrite_message(issues)},
        ]

    _, draft, issues = best
    specs = build_specs(draft, product)
    missing_specs = [f"{spec.name}: нет во входных данных" for spec in specs if spec.value == NO_DATA]
    specs += empty_rows(parsed.empty_specs, specs)
    if thin:
        issues = [*issues, THIN_WARNING]
    clarifications = [item for item in draft.clarifications if item.strip()]
    card = Card(
        seo_title=draft.seo_title.strip(),
        seo_description=draft.seo_description.strip(),
        key_specs=specs,
        search_queries=unique_queries(draft.search_queries),
        commercial=draft.commercial,
    )
    result = CardResult(
        status="needs_review" if issues or clarifications else "ready",
        card=card,
        missing_data=parsed.missing + missing_specs + clarifications,
        warnings=issues,
        rewrites=rewrites,
    )
    result.markdown = to_markdown(result)
    return result
