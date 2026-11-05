"""Проверка черновика кодом. Модели на слово не верим: числа, единицы и длины считаем сами."""

import re

from .schemas import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    QUERIES_MAX,
    QUERIES_MIN,
    TITLE_MAX,
    LlmDraft,
    ProductInput,
)

NUMBER = r"\d+(?:[.,]\d+)?"
UNITS = (
    "МПа|кПа|гПа|Па|мбар|бар|атм|мА|мкА|кВт|Вт|кВА|ВА|мВ|кВ|В|А|кГц|МГц|Гц|"
    "мкм|мм|см|км|м3/ч|л/мин|м/с|м|кг|г|мс|мин|сек|с|ч|°С|°|%"
)
# Несколько чисел с одной единицей: 0...100 гПа, 50, 60 Гц, 48×48×103 мм
JOIN = r"\s*(?:\.{2,}|…|-|–|—|−|÷|/|,|×|х|x|\*|до|и)\s*"
VALUE_PATTERN = (
    rf"(?<![\w.,])({NUMBER}(?:{JOIN}[+\-–−]?{NUMBER})*)\s*({UNITS})(?![а-яА-Яa-zA-Z0-9])"
)
VALUE_GROUP = re.compile(VALUE_PATTERN)
# Запросы пишутся в нижнем регистре, там единицы сравниваются без учета регистра
VALUE_GROUP_ANY_CASE = re.compile(VALUE_PATTERN, re.IGNORECASE)
UNIT_IN_KEY = re.compile(rf",\s*({UNITS})\s*$")
LATIN_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:[-/+.][A-Za-z0-9]+)*")

# Утверждения, за которые отвечает магазин. Без них во входных данных их быть не должно.
RISKY_CLAIMS = {
    "гост": "ГОСТ",
    "сертифик": "сертификаты",
    "поверк": "поверка",
    "поверен": "поверка",
    "госреестр": "госреестр",
    "взрывозащ": "взрывозащита",
    "гаранти": "гарантия",
    "доставк": "доставка",
    "в наличии": "наличие",
}


# Свойства и области применения, которые модель любит дописывать от себя
UNSUPPORTED_WORDS = (
    "надежн", "компактн", "долговечн", "простот", "легко", "высокоточ", "точного",
    "широк", "лаборатор", "вентиляц", "гидравл", "трубопровод", "нефт", "газов", "пищев", "энергетик",
    "мобильн", "полев", "площадк", "совместим", "интеграц", "интегрир", "переходник", "удобн",
    "безопасн", "технологическ", "мониторинг", "большинств",
)

# Однобуквенные единицы похожи на предлоги: «DM 02 с резьбой» это не 2 секунды
AMBIGUOUS_UNITS = {"с", "в", "м", "г", "а"}

# Меньше этого объема исходных данных честно написать 800 символов почти невозможно
THIN_SOURCE_CHARS = 300


def _clean(text: str) -> str:
    text = text.replace(" ", " ").replace(" ", " ").replace("‑", "-")
    text = re.sub(r"°\s*[CcСс]\b", "°С", text)
    text = re.sub(r"(?<![\d.,])([1-9]\d{0,2}) (?=\d{3}(?!\d))", r"\1", text)
    return text


def _number(raw: str) -> str:
    value = raw.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def numbers_in(text: str) -> set[str]:
    return {_number(found) for found in re.findall(NUMBER, _clean(text))}


def values_in(text: str, pattern: re.Pattern = VALUE_GROUP) -> set[tuple[str, str]]:
    pairs = set()
    for group in pattern.finditer(_clean(text)):
        unit = group.group(2)
        for number in re.findall(NUMBER, group.group(1)):
            pairs.add((_number(number), unit))
    return pairs


def source_text(product: ProductInput) -> str:
    lines = []
    for key, value in product.specs.items():
        # Единица может стоять в названии поля: «Масса, кг»: «1,5»
        unit = UNIT_IN_KEY.search(key)
        lines.append(f"{key}: {value} {unit.group(1)}" if unit else f"{key}: {value}")
    return " ".join([product.name, product.manufacturer, *lines, product.description])


def generated_text(draft: LlmDraft) -> str:
    return "\n".join(
        [
            draft.seo_title,
            draft.seo_description,
            draft.commercial.audience,
            *draft.commercial.tasks,
        ]
    )


def check_facts(draft: LlmDraft, product: ProductInput) -> list[str]:
    source = source_text(product)
    prose = generated_text(draft)
    queries = "\n".join(draft.search_queries)
    output = f"{prose}\n{queries}"
    issues = []

    source_numbers = numbers_in(source)
    source_values = values_in(source)
    name_numbers = numbers_in(product.name)
    flagged_numbers = set()

    def is_model_number(number: str, unit: str) -> bool:
        return number in name_numbers and unit.lower() in AMBIGUOUS_UNITS

    for number, unit in sorted(values_in(prose)):
        if (number, unit) not in source_values and not is_model_number(number, unit):
            flagged_numbers.add(number)
            issues.append(f"Значения «{number} {unit}» нет во входных данных")
    source_lower_values = {(number, unit.lower()) for number, unit in source_values}
    for number, unit in sorted(values_in(queries, VALUE_GROUP_ANY_CASE)):
        if (number, unit.lower()) not in source_lower_values and not is_model_number(number, unit):
            flagged_numbers.add(number)
            issues.append(f"Значения «{number} {unit}» в запросах нет во входных данных")
    for number in sorted(numbers_in(output) - source_numbers - flagged_numbers):
        issues.append(f"Числа «{number}» нет во входных данных")

    # Подписи пустых строк проверяю только на числа: промпт сам просит называть там то, чего нет
    labels = " ".join(item.label for item in draft.key_specs if item.source_key is None)
    for number in sorted(numbers_in(labels) - source_numbers):
        issues.append(f"Числа «{number}» в подписи характеристики нет во входных данных")

    source_lower = source.lower()
    source_tokens = {token.lower() for token in LATIN_TOKEN.findall(source)}
    for token in sorted(set(LATIN_TOKEN.findall(output))):
        if token.lower() not in source_tokens:
            issues.append(f"Обозначения «{token}» нет во входных данных")

    source_lower = source_lower.replace("ё", "е")
    output_lower = output.lower().replace("ё", "е")
    for stem in UNSUPPORTED_WORDS:
        found = re.search(rf"\b{stem}\w*", output_lower)
        if found and stem not in source_lower:
            issues.append(f"Слова «{found.group()}» нет во входных данных, убери или подтверди фактом")

    for stem, label in RISKY_CLAIMS.items():
        found = re.search(rf"{stem}\w*", output_lower)
        if found and stem not in source_lower:
            issues.append(f"Упоминается {label} («{found.group()}»), во входных данных этого нет")
    return issues


def is_thin(product: ProductInput) -> bool:
    specs = " ".join(product.specs.values())
    return len(specs) + len(product.description) < THIN_SOURCE_CHARS


def check_queries(draft: LlmDraft, product: ProductInput) -> list[str]:
    """В запросе должна быть хотя бы одна основа слова из названия товара."""
    words = re.findall(r"[а-яёa-z0-9]{2,}", product.name.lower())
    stems = {word[:5] for word in words if len(word) >= 3}
    # Короткие части модели (dm, 02) сравниваю целиком, русские предлоги не считаю
    short = {word for word in words if len(word) == 2 and not re.fullmatch(r"[а-яё]+", word)}

    def mentions_product(query: str) -> bool:
        query = query.lower()
        return any(stem in query for stem in stems) or bool(short & set(re.findall(r"[а-яёa-z0-9]+", query)))

    return [
        f"В запросе «{query}» нет типа прибора или модели"
        for query in draft.search_queries
        if not mentions_product(query)
    ]


def check_format(draft: LlmDraft, thin: bool = False) -> list[str]:
    issues = []
    title = len(draft.seo_title.strip())
    if not title or title > TITLE_MAX:
        issues.append(f"SEO-заголовок {title} символов, нужно до {TITLE_MAX}")
    description = len(draft.seo_description.strip())
    too_short = description < DESCRIPTION_MIN and not (thin and description)
    if too_short or description > DESCRIPTION_MAX:
        issues.append(
            f"SEO-описание {description} символов, нужно {DESCRIPTION_MIN}-{DESCRIPTION_MAX}"
        )
    queries = len({q.strip().lower() for q in draft.search_queries if q.strip()})
    if not QUERIES_MIN <= queries <= QUERIES_MAX:
        issues.append(f"Поисковых запросов {queries}, нужно {QUERIES_MIN}-{QUERIES_MAX}")
    if not draft.key_specs:
        issues.append("Список характеристик пуст")
    if not draft.commercial.audience.strip() or not draft.commercial.tasks:
        issues.append("Commercial-блок заполнен не полностью")
    return issues


def check_spec_keys(draft: LlmDraft, product: ProductInput) -> list[str]:
    return [
        f"Ключа «{item.source_key}» нет в specs, укажи точный ключ или null"
        for item in draft.key_specs
        if item.source_key is not None and item.source_key not in product.specs
    ] + [
        f"Ключа «{key}» нет в specs, укажи точный ключ"
        for keys in draft.core_specs.model_dump().values()
        for key in keys
        if key not in product.specs
    ]


def check_draft(draft: LlmDraft, product: ProductInput) -> list[str]:
    return (
        check_format(draft, is_thin(product))
        + check_spec_keys(draft, product)
        + check_queries(draft, product)
        + check_facts(draft, product)
    )
