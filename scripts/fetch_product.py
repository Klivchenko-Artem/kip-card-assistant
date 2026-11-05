"""Собирает входной JSON для сервиса из YML-фида и страницы товара на souz-pribor.ru.

В фиде есть только название, тип, производитель и цена, поэтому характеристики
и описание берутся со страницы товара, ссылка на которую лежит в фиде.

Пример: python scripts/fetch_product.py 58444 --out examples/input/testo-510.json
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

FEED_URL = "https://www.souz-pribor.ru/yml/any/feed.xml"
CACHE = Path(".cache/feed.xml")
HEADERS = {"User-Agent": "Mozilla/5.0 (kip-card-assistant)"}


def load_feed() -> Path:
    if CACHE.exists():
        return CACHE
    CACHE.parent.mkdir(exist_ok=True)
    part = CACHE.with_suffix(".part")
    with httpx.stream("GET", FEED_URL, headers=HEADERS, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with part.open("wb") as file:
            for chunk in r.iter_bytes():
                file.write(chunk)
    part.replace(CACHE)
    return CACHE


def find_offer(feed: Path, offer_id: str) -> dict:
    for _, element in ET.iterparse(feed, events=("end",)):
        if element.tag != "offer":
            continue
        if element.get("id") == offer_id:
            return {
                "name": element.findtext("name", ""),
                "type": element.findtext("typePrefix", ""),
                "vendor": element.findtext("vendor", ""),
                "url": element.findtext("url", ""),
            }
        element.clear()
    raise SystemExit(f"Товар {offer_id} в фиде не найден")


def squeeze(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def summary_specs(soup: BeautifulSoup) -> dict[str, str]:
    """Короткий блок рядом с ценой: подпись и значение идут парами."""
    specs = {}
    for item in soup.select(".characteristics .characteristics__item"):
        name = item.select_one(".characteristics__name")
        value = item.select_one(".characteristics__desc")
        if name and value:
            specs[squeeze(name.get_text(" ")).rstrip(":")] = squeeze(value.get_text(" "))
    return specs


def put(specs: dict[str, str], key: str, value: str) -> None:
    """Одинаковые ключи на странице не должны затирать друг друга."""
    unique, number = key, 2
    while unique in specs:
        unique, number = f"{key} ({number})", number + 1
    specs[unique] = value


def wide_table_text(rows: list[list[str]]) -> str:
    if rows[0] and rows[0][0] != "Обозначение":
        return "; ".join(" / ".join(row) for row in rows if len(row) >= 3)
    # Таблица датчиков. Коэффициент W100 в карточке не нужен, а токенов съедает много
    lines = []
    for row in rows[1:]:
        if len(row) >= 3:
            name = re.sub(r"\s*W100=\S+", "", row[1])
            lines.append(f"{name}: {row[2]}")
    return "; ".join(lines)


def table_specs(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for table in soup.select("#specifications table"):
        group = ""
        rows = [[squeeze(c.get_text(" ")) for c in r.select("td,th")] for r in table.select("tr")]
        if any(len(row) >= 3 for row in rows):
            # Широкая таблица идет одной строкой под своим заголовком
            heading = table.find_previous(["h2", "h3"])
            title = squeeze(heading.get_text(" ")) if heading else "Таблица"
            put(specs, title, wide_table_text(rows))
            continue
        for row in rows:
            if len(row) == 1:
                group = row[0].rstrip(":")
            elif len(row) == 2 and row[0] and row[1]:
                if row[1].lower().startswith("см. таблицу"):
                    continue
                key = row[0].rstrip(":")
                if key.startswith("-") or key in specs:
                    key = f"{group} {key}".strip()
                put(specs, key, row[1])
    return specs


def merge_specs(summary: dict[str, str], table: dict[str, str]) -> dict[str, str]:
    """Разные значения под одним именем оставляю оба: это повод для вопроса менеджеру."""
    specs = dict(summary)
    for key, value in table.items():
        if specs.get(key) != value:
            put(specs, key, value)
    return specs


def description_text(soup: BeautifulSoup) -> str:
    block = soup.select_one("#description .long-short-block__inner")
    if block is None:
        return ""
    parts = [squeeze(node.get_text(" ")) for node in block.find_all(["p", "h2", "h3", "li"])]
    return "\n".join(part for part in parts if part)


def build_input(offer: dict, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = f"{offer['type']} {offer['name']}".strip()
    return {
        "name": title[:1].upper() + title[1:],
        "manufacturer": offer["vendor"],
        "specs": merge_specs(summary_specs(soup), table_specs(soup)),
        "description": description_text(soup),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("offer_id")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    offer = find_offer(load_feed(), args.offer_id)
    response = httpx.get(offer["url"], headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()
    data = build_input(offer, response.text)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(f"{data['name']}: характеристик {len(data['specs'])}, описание {len(data['description'])} симв.")


if __name__ == "__main__":
    main()
