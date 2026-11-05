from app.checks import check_draft, check_facts, check_format, check_queries, numbers_in, values_in
from app.schemas import Commercial, CoreSpecs, ProductInput, SpecChoice
from tests.helpers import GOOD_TEXT, PRODUCT, make_draft


def test_clean_draft_passes():
    assert check_draft(make_draft(), PRODUCT) == []


def test_title_length():
    issues = check_format(make_draft(seo_title="М" * 71))
    assert issues == ["SEO-заголовок 71 символов, нужно до 70"]
    assert check_format(make_draft(seo_title="М" * 70)) == []


def test_description_length_borders():
    assert check_format(make_draft(seo_description="а" * 800)) == []
    assert check_format(make_draft(seo_description="а" * 1200)) == []
    assert "799" in check_format(make_draft(seo_description="а" * 799))[0]
    assert "1201" in check_format(make_draft(seo_description="а" * 1201))[0]


def test_duplicate_queries_do_not_count():
    issues = check_format(make_draft(search_queries=["манометр", "Манометр ", "dm 02"]))
    assert issues == ["Поисковых запросов 2, нужно 3-5"]


def test_empty_commercial():
    draft = make_draft(commercial=Commercial(audience=" ", tasks=[]))
    assert check_format(draft) == ["Commercial-блок заполнен не полностью"]


def test_invented_number_is_caught():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " Вес 350 г."), PRODUCT)
    assert issues == ["Значения «350 г» нет во входных данных"]


def test_known_number_with_other_unit_is_caught():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " Диаметр 100 см."), PRODUCT)
    assert issues == ["Значения «100 см» нет во входных данных"]


def test_converted_units_are_caught():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " До 16 бар."), PRODUCT)
    assert issues == ["Значения «16 бар» нет во входных данных"]


def test_number_without_unit_is_caught():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " Модель 2024 года."), PRODUCT)
    assert issues == ["Числа «2024» нет во входных данных"]


def test_invented_interface_is_caught():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " Выход RS-485."), PRODUCT)
    assert "Обозначения «RS-485» нет во входных данных" in issues


def test_risky_claims_are_caught():
    text = GOOD_TEXT + " Соответствует ГОСТ, прошел поверку, есть сертификат."
    issues = " ".join(check_facts(make_draft(seo_description=text), PRODUCT))
    assert "ГОСТ" in issues and "поверка" in issues and "сертификаты" in issues


def test_claim_from_source_is_allowed():
    product = PRODUCT.model_copy(update={"description": "Гарантия 2 года."})
    issues = check_facts(make_draft(seo_description="Гарантия 2 года, DM 02."), product)
    assert not any("гарантия" in issue for issue in issues)


def test_unknown_spec_key():
    draft = make_draft(key_specs=[SpecChoice(label="Питание", source_key="питание")])
    assert "Ключа «питание» нет в specs, укажи точный ключ или null" in check_draft(draft, PRODUCT)


def test_number_formats_are_equal():
    assert numbers_in("1,50 и 1.5") == {"1.5"}
    assert numbers_in("1 200 символов") == {"1200"}
    assert numbers_in("давление 0 100 гпа") == {"0", "100"}


def test_unit_is_shared_inside_a_range():
    assert values_in("0 ... 100 гПа") == {("0", "гПа"), ("100", "гПа")}
    assert values_in("50, 60 Гц") == {("50", "Гц"), ("60", "Гц")}
    assert values_in("48×48×103 мм") == {("48", "мм"), ("103", "мм")}
    assert values_in("от 0 до 50 °C") == {("0", "°С"), ("50", "°С")}


def test_similar_units_are_different():
    assert values_in("250 Вт") == {("250", "Вт")}
    assert values_in("250 В") == {("250", "В")}


def test_empty_description_in_source():
    product = ProductInput(name="ТРМ1", specs={"питание": "24 В"})
    assert check_facts(make_draft(seo_title="ТРМ1 24 В", seo_description="ТРМ1", search_queries=[],
                                  commercial=Commercial(audience="КИПиА", tasks=[])), product) == []


def test_invented_properties_are_caught():
    text = GOOD_TEXT + " Надёжный прибор для систем вентиляции."
    issues = " ".join(check_facts(make_draft(seo_description=text), PRODUCT))
    assert "надежный" in issues and "вентиляции" in issues


def test_property_from_source_is_allowed():
    product = PRODUCT.model_copy(update={"description": "Надёжная работа в системах вентиляции."})
    text = "Надежный манометр DM 02 для вентиляции."
    assert check_facts(make_draft(seo_description=text), product) == []


def test_query_without_product_is_caught():
    draft = make_draft(search_queries=["манометр dm 02", "манометр манотомь", "батарейки ааа"])
    assert check_draft(draft, PRODUCT) == ["В запросе «батарейки ааа» нет типа прибора или модели"]


def test_unknown_core_key():
    draft = make_draft(core_specs=CoreSpecs(power=["питание"]))
    assert "Ключа «питание» нет в specs, укажи точный ключ" in check_draft(draft, PRODUCT)


def test_short_description_is_allowed_only_for_thin_source():
    assert check_format(make_draft(seo_description="Коротко."), thin=True) == []
    assert check_format(make_draft(seo_description="Коротко."))
    assert check_format(make_draft(seo_description=""), thin=True)


def test_unit_in_key_and_two_dots_range():
    product = ProductInput(
        name="Датчик ДД",
        specs={"Напряжение питания, В": "24", "Масса, кг": "1,5", "Диапазон": "0..100 гПа"},
    )
    text = "Питание 24 В, масса 1,5 кг, диапазон 0 до 100 гПа."
    assert check_facts(make_draft(seo_title="Датчик ДД", seo_description=text, search_queries=[],
                                  commercial=Commercial(audience="КИПиА", tasks=[]), key_specs=[]), product) == []


def test_preposition_after_model_number_is_not_a_unit():
    text = GOOD_TEXT + " Манометр DM 02 с резьбой."
    assert check_facts(make_draft(seo_description=text), PRODUCT) == []


def test_empty_row_label_may_name_absent_things():
    draft = make_draft(key_specs=[SpecChoice(label="Взрывозащита IP", source_key=None)])
    assert check_facts(draft, PRODUCT) == []


def test_part_of_designation_is_not_enough():
    issues = check_facts(make_draft(seo_description=GOOD_TEXT + " Резьба G1."), PRODUCT)
    assert "Обозначения «G1» нет во входных данных" in issues


def test_preposition_in_name_does_not_pass_a_query():
    product = ProductInput(name="Датчик температуры на DIN-рейку", description="текст")
    draft = make_draft(search_queries=["батарейки на ааа"])
    assert check_queries(draft, product)


def test_invented_label_is_checked():
    draft = make_draft(key_specs=[SpecChoice(label="Диапазон 0-500 бар", source_key=None)])
    assert any("500" in issue for issue in check_facts(draft, PRODUCT))


def test_unit_swap_in_lowercase_query_is_caught():
    draft = make_draft(search_queries=["манометр 1,6 кпа", "манометр dm 02", "манометр манотомь"])
    assert "Значения «1.6 кпа» в запросах нет во входных данных" in check_facts(draft, PRODUCT)


def test_short_model_name_counts_in_queries():
    product = ProductInput(name="DM 02", description="текст")
    draft = make_draft(search_queries=["dm 02 цена", "dm 02", "dm 02 манометр"])
    assert check_queries(draft, product) == []


def test_size_with_latin_x_is_not_a_token():
    product = PRODUCT.model_copy(update={"description": "Размер 48x48x103 мм."})
    assert check_facts(make_draft(seo_description="DM 02, размер 48x48x103 мм."), product) == []
