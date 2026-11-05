import json

import pytest

from app.input_check import InputError, parse_input


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("", "Пустой запрос"),
        ("{oops", "Некорректный JSON"),
        ("[1, 2]", "JSON-объект"),
        ('{"manufacturer": "ОВЕН"}', "name"),
        ('{"name": "   ", "description": "текст"}', "name"),
        ('{"name": "Прибор", "specs": ["a"], "description": "текст"}', "specs"),
        ('{"name": "Прибор"}', "не из чего"),
        ('{"name": "Прибор", "specs": {"a": ""}, "description": " "}', "не из чего"),
        ('{"name": {"a": 1}, "description": "текст"}', "строками или числами"),
    ],
)
def test_bad_input_gets_clear_message(raw, fragment):
    with pytest.raises(InputError, match=fragment):
        parse_input(raw)


def test_broken_encoding():
    with pytest.raises(InputError, match="UTF-8"):
        parse_input('{"name": "Прибор"}'.encode("cp1251"))


def test_missing_fields_are_reported():
    raw = json.dumps(
        {"name": "Прибор", "specs": {"класс точности": "", "питание": "24 В"}},
        ensure_ascii=False,
    )
    result = parse_input(raw)
    assert result.product.specs == {"питание": "24 В"}
    assert "Производитель (manufacturer)" in result.missing
    assert "Описание (description)" in result.missing
    assert any("класс точности" in item for item in result.missing)


def test_numbers_and_placeholders_in_specs():
    raw = '{"name": "Прибор", "manufacturer": "-", "specs": {"каналы": 2, "вес": "н/д", "x": null}}'
    result = parse_input(raw)
    assert result.product.specs == {"каналы": "2"}
    assert "Производитель (manufacturer)" in result.missing


def test_bom_is_accepted():
    raw = b"\xef\xbb\xbf" + '{"name": "Прибор", "description": "текст"}'.encode()
    assert parse_input(raw).product.name == "Прибор"


def test_deep_json_is_input_error():
    with pytest.raises(InputError, match="вложенность"):
        parse_input("[" * 200000)


def test_bool_spec_is_kept():
    raw = '{"name": "Прибор", "specs": {"дисплей": true, "wifi": false}}'
    assert parse_input(raw).product.specs == {"дисплей": "да", "wifi": "нет"}
