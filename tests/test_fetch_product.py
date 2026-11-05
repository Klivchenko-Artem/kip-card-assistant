from scripts.fetch_product import build_input

OFFER = {"name": "ТРМ1", "type": "измеритель-регулятор", "vendor": "ОВЕН", "url": ""}
HTML = """
<div class="characteristics"><div class="characteristics__title">Характеристики</div>
  <div class="characteristics__item"><span class="characteristics__name">Кол-во каналов:</span>
  <span class="characteristics__desc">1</span></div>
  <div class="characteristics__item"><span class="characteristics__name">Расход:</span>
  <span class="characteristics__desc">10 м<sup>3</sup>/ч</span></div>
  <a>Все характеристики</a></div>
<div id="description"><div class="long-short-block__inner">
  <h2>Описание</h2><p>Первый   абзац.</p><ul><li>Пункт</li></ul></div></div>
<div id="specifications">
  <table><tr><td>Напряжение питания</td><td>24 В</td></tr>
  <tr><td>Типы датчиков</td><td>см. таблицу ниже</td></tr>
  <tr><td>Погрешность:</td></tr><tr><td>- для термопар</td><td>0,5 %</td></tr></table>
  <h3>Датчики</h3>
  <table><tr><td>Обозначение</td><td>Тип</td><td>Диапазон</td><td>Шаг</td></tr>
  <tr><td>P100</td><td>Pt100</td><td>0...100 °С</td><td>0,1 °С</td></tr></table>
</div>
"""


def test_page_is_turned_into_input():
    data = build_input(OFFER, HTML)
    assert data["name"] == "Измеритель-регулятор ТРМ1"
    assert data["manufacturer"] == "ОВЕН"
    assert data["description"] == "Описание\nПервый абзац.\nПункт"
    assert data["specs"] == {
        "Кол-во каналов": "1",
        "Расход": "10 м 3 /ч",
        "Напряжение питания": "24 В",
        "Погрешность - для термопар": "0,5 %",
        "Датчики": "Pt100: 0...100 °С",
    }


def test_page_without_blocks():
    data = build_input(OFFER, "<html></html>")
    assert data["specs"] == {}
    assert data["description"] == ""


def test_other_wide_table_and_duplicates_are_kept():
    html = """<div id="specifications"><h3>Х</h3>
    <table><tr><td>Параметр</td><td>А</td><td>Б</td></tr><tr><td>Вес</td><td>1</td><td>2</td></tr></table>
    <table><tr><td>Обозначение</td><td>Тип</td><td>Диапазон</td></tr><tr><td>P</td><td>Pt100 W100=1.385</td><td>0...5</td></tr></table>
    <table><tr><td>Вес</td><td>1 кг</td></tr><tr><td>Вес</td><td>2 кг</td></tr></table></div>"""
    specs = build_input(OFFER, html)["specs"]
    assert specs["Х"] == "Параметр / А / Б; Вес / 1 / 2"
    assert specs["Х (2)"] == "Pt100: 0...5"
    assert specs["Вес"] == "1 кг" and specs["Вес (2)"] == "2 кг"


def test_different_values_under_one_name_are_both_kept():
    html = """<div class="characteristics"><div class="characteristics__item">
    <span class="characteristics__name">Размер:</span><span class="characteristics__desc">102 мм</span></div></div>
    <div id="specifications"><table><tr><td>Размер</td><td>103 мм</td></tr></table></div>"""
    assert build_input(OFFER, html)["specs"] == {"Размер": "102 мм", "Размер (2)": "103 мм"}
