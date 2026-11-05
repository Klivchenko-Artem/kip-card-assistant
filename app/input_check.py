"""Разбор входных данных. Все, что можно понять без модели, решается здесь."""

import json
from dataclasses import dataclass, field

from .schemas import ProductInput

EMPTY_VALUES = {"", "-", "–", "—", "нет данных", "данных нет", "н/д", "n/a", "null", "none"}


class InputError(Exception):
    """Текст ошибки показывается пользователю как есть."""


@dataclass
class ParsedInput:
    product: ProductInput
    missing: list[str]
    empty_specs: list[str] = field(default_factory=list)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return "" if cleaned.lower() in EMPTY_VALUES else cleaned
    raise InputError("Значения полей должны быть строками или числами.")


def parse_json(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise InputError("Файл не в кодировке UTF-8.") from None
    if not raw.strip():
        raise InputError("Пустой запрос: передайте JSON с данными о товаре.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"Некорректный JSON: строка {exc.lineno}, символ {exc.colno}."
        ) from None
    except RecursionError:
        raise InputError("Некорректный JSON: слишком большая вложенность.") from None
    if not isinstance(data, dict):
        raise InputError("Ожидается JSON-объект с полями name, manufacturer, specs, description.")
    return data


def normalize(data: dict) -> ParsedInput:
    name = _text(data.get("name"))
    if not name:
        raise InputError("Не заполнено поле name: без названия карточку не собрать.")

    raw_specs = data.get("specs") or {}
    if not isinstance(raw_specs, dict):
        raise InputError('Поле specs должно быть объектом вида {"характеристика": "значение"}.')

    specs: dict[str, str] = {}
    missing: list[str] = []
    empty_specs: list[str] = []
    for key, value in raw_specs.items():
        key = str(key).strip()
        if not key:
            continue
        cleaned = _text(value)
        if cleaned:
            specs[key] = cleaned
        else:
            empty_specs.append(key)
            missing.append(f"Характеристика «{key}»: значение не заполнено")

    manufacturer = _text(data.get("manufacturer"))
    description = _text(data.get("description"))

    if not specs and not description:
        raise InputError(
            "Нет ни характеристик (specs), ни описания (description). "
            "Писать карточку не из чего, модели пришлось бы выдумывать."
        )
    if not manufacturer:
        missing.append("Производитель (manufacturer)")
    if not specs:
        missing.append("Характеристики (specs)")
    if not description:
        missing.append("Описание (description)")

    product = ProductInput(
        name=name, manufacturer=manufacturer, specs=specs, description=description
    )
    return ParsedInput(product=product, missing=missing, empty_specs=empty_specs)


def parse_input(raw: str | bytes) -> ParsedInput:
    return normalize(parse_json(raw))
