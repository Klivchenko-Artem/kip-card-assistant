import pytest

from app.generator import clean_text, fit_description, generate_card
from app.llm import LlmUnavailable
from app.input_check import ParsedInput
from app.schemas import NO_DATA, CoreSpecs, SpecChoice
from tests.helpers import GOOD_TEXT, PRODUCT, FakeClient, make_draft, parsed


def test_values_come_from_input_not_from_model():
    result = generate_card(parsed(), FakeClient(make_draft()), 2)
    specs = {s.name: s.value for s in result.card.key_specs}
    assert specs["Диапазон измерений"] == "0–1,6 МПа"
    assert specs["Присоединение"] == "G1/2"
    assert specs["Питание"] == NO_DATA
    assert specs["Интерфейсы"] == NO_DATA
    assert specs["Материал корпуса"] == NO_DATA
    assert any("Материал корпуса" in item for item in result.missing_data)
    assert result.rewrites == 0


def test_rewrite_sends_issues_back_to_model():
    bad = make_draft(seo_title="М" * 90)
    client = FakeClient(bad, make_draft())
    result = generate_card(parsed(), client, 2)
    assert result.rewrites == 1
    last = client.calls[1]
    assert last[2]["role"] == "assistant"
    assert "90 символов" in last[3]["content"]


def test_gives_up_and_marks_for_review():
    bad = make_draft(seo_description=GOOD_TEXT + " Вес 350 г.")
    client = FakeClient(bad, bad, bad)
    result = generate_card(parsed(), client, 2)
    assert result.status == "needs_review"
    assert result.rewrites == 2
    assert len(client.calls) == 3
    assert "350 г" in result.warnings[0]
    assert "Проверить вручную" in result.markdown


def test_best_attempt_is_kept():
    worse = make_draft(seo_title="М" * 90, seo_description=GOOD_TEXT + " Вес 350 г.")
    better = make_draft(seo_description=GOOD_TEXT + " Вес 350 г.")
    much_worse = make_draft(seo_title="М" * 90, seo_description="Вес 350 г и 7 кг.")
    result = generate_card(parsed(), FakeClient(worse, better, much_worse), 2)
    assert len(result.card.seo_title) <= 70
    assert not any("заголовок" in item for item in result.warnings)


def test_unknown_key_turns_into_no_data():
    draft = make_draft(key_specs=[SpecChoice(label="Вес", source_key="вес 1 кг")])
    result = generate_card(parsed(), FakeClient(draft), 0)
    assert {s.name: s.value for s in result.card.key_specs}["Вес"] == NO_DATA
    assert result.status == "needs_review"


def test_input_gaps_and_model_questions_are_merged():
    draft = make_draft(clarifications=["Размер в описании и таблице разный"])
    result = generate_card(parsed(["Описание (description)"]), FakeClient(draft), 0)
    assert result.missing_data[0] == "Описание (description)"
    assert result.missing_data[-1] == "Размер в описании и таблице разный"
    assert "## Уточнить" in result.markdown


def test_dash_in_ranges_survives():
    text = "Диапазон 0 \u2013 1,6 МПа, от \u2013 50 °С, 100 °С \u2013 200 °С"
    assert clean_text(text) == text


def test_long_units_and_negative_ranges_keep_dash():
    assert clean_text("10 мбар \u2013 20 мбар") == "10 мбар \u2013 20 мбар"
    assert clean_text("-50 °С \u2013 \u221220 °С") == "-50 °С \u2013 \u221220 °С"


def test_cut_only_at_real_sentence_end():
    head = "Прибор работает стабильно. " * 44
    text = head + "Точность ±0.03 гПа с ТРМ1-Щ5.У2.С и защит. крышкой в щите."
    fitted = fit_description(text.strip())
    assert fitted == head.strip()[: len(fitted)]
    assert fitted.endswith("стабильно.")


def test_real_value_fills_empty_core_row_by_key():
    product = PRODUCT.model_copy(update={"specs": {**PRODUCT.specs, "питание": "24 В"}})
    draft = make_draft(key_specs=[SpecChoice(label="Напряжение", source_key="питание")])
    result = generate_card(ParsedInput(product=product, missing=[]), FakeClient(draft), 0)
    assert {s.name: s.value for s in result.card.key_specs}["Питание"] == "24 В"
    assert not any(item.startswith("Питание") for item in result.missing_data)


def test_other_key_does_not_take_a_core_label():
    draft = make_draft(core_specs=CoreSpecs(), key_specs=[SpecChoice(label="Питание", source_key="присоединение")])
    result = generate_card(parsed(), FakeClient(draft), 0)
    specs = {s.name: s.value for s in result.card.key_specs}
    assert specs["Питание"] == NO_DATA and specs["Присоединение"] == "G1/2"


def test_row_name_comes_from_input_key():
    draft = make_draft(key_specs=[SpecChoice(label="Рабочая температура", source_key="присоединение")])
    result = generate_card(parsed(), FakeClient(draft), 0)
    names = {s.name for s in result.card.key_specs}
    assert "Рабочая температура" not in names and "Присоединение" in names


def test_empty_description_does_not_beat_real_text():
    first = make_draft(seo_description=GOOD_TEXT + " Надежный и компактный.")
    second = make_draft(seo_description="")
    result = generate_card(parsed(), FakeClient(first, second), 1)
    assert result.card.seo_description


def test_queries_are_deduplicated_ignoring_case():
    draft = make_draft(search_queries=["манометр dm 02", "Манометр DM 02", "манометр манотомь", "dm 02"])
    result = generate_card(parsed(), FakeClient(draft), 0)
    assert result.card.search_queries == ["манометр dm 02", "манометр манотомь", "dm 02"]


def test_text_cleanup():
    assert clean_text("Частота – 0,5 с, диапазон 0‑100 гПа") == "Частота: 0,5 с, диапазон 0-100 гПа"
    assert clean_text("–50…+200 °С") == "–50…+200 °С"


def test_long_description_loses_whole_sentences():
    text = "Предложение про прибор. " * 52
    fitted = fit_description(text.strip())
    assert 800 <= len(fitted) <= 1200
    assert fitted.endswith(".")


def test_description_is_not_cut_below_minimum():
    text = "а" * 700 + ". " + "б" * 600 + "."
    assert fit_description(text) == text


class LimitAfterFirst(FakeClient):
    def complete(self, messages):
        if self.calls:
            raise LlmUnavailable("лимит")
        return super().complete(messages)


def test_limit_during_rewrite_keeps_the_draft():
    bad = make_draft(seo_title="М" * 90)
    result = generate_card(parsed(), LimitAfterFirst(bad), 2)
    assert result.status == "needs_review"
    assert result.warnings


def test_limit_on_first_request_is_an_error():
    client = LimitAfterFirst()
    client.calls.append([])
    with pytest.raises(LlmUnavailable):
        generate_card(parsed(), client, 2)


def test_empty_specs_are_shown_as_no_data():
    data = parsed()
    data.empty_specs = ["материал мембраны"]
    result = generate_card(data, FakeClient(make_draft()), 0)
    specs = {s.name: s.value for s in result.card.key_specs}
    assert specs["материал мембраны"] == NO_DATA


def test_empty_spec_does_not_duplicate_core_row():
    data = parsed()
    data.empty_specs = ["напряжение питания"]
    result = generate_card(data, FakeClient(make_draft()), 0)
    assert "напряжение питания" not in {s.name for s in result.card.key_specs}


def test_useless_rows_are_dropped():
    draft = make_draft(key_specs=[SpecChoice(label="Тип прибора", source_key=None)])
    result = generate_card(parsed(), FakeClient(draft), 0)
    assert "Тип прибора" not in {s.name for s in result.card.key_specs}


def test_thin_source_needs_review():
    result = generate_card(parsed(), FakeClient(make_draft()), 0)
    assert result.status == "needs_review"
    assert "мало" in result.warnings[-1]


def test_several_keys_for_one_core_spec():
    draft = make_draft(core_specs=CoreSpecs(range=["диапазон измерений", "присоединение"]))
    result = generate_card(parsed(), FakeClient(draft), 0)
    value = result.card.key_specs[0].value
    assert "диапазон измерений: 0\u20131,6 МПа" in value and "присоединение: G1/2" in value


def test_key_used_in_core_is_not_repeated():
    draft = make_draft(key_specs=[SpecChoice(label="Шкала", source_key="диапазон измерений")])
    result = generate_card(parsed(), FakeClient(draft), 0)
    assert "Шкала" not in {s.name for s in result.card.key_specs}


def test_clarifications_need_review():
    product = PRODUCT.model_copy(update={"description": "Подробное описание прибора. " * 20})
    data = ParsedInput(product=product, missing=[])
    clean = generate_card(data, FakeClient(make_draft()), 0)
    assert clean.status == "ready"
    draft = make_draft(clarifications=["Разные размеры: 102 и 103 мм"])
    assert generate_card(data, FakeClient(draft), 0).status == "needs_review"
