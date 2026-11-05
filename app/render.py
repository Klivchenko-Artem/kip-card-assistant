from .schemas import CardResult


def to_markdown(result: CardResult) -> str:
    card = result.card
    lines = [
        f"## SEO-заголовок ({len(card.seo_title)} симв.)",
        "",
        card.seo_title,
        "",
        f"## SEO-описание ({len(card.seo_description)} симв.)",
        "",
        card.seo_description,
        "",
        "## Характеристики",
        "",
        "| Характеристика | Значение |",
        "| --- | --- |",
    ]
    lines += [f"| {s.name} | {s.value.replace('|', '/')} |" for s in card.key_specs]
    lines += ["", "## Поисковые запросы", ""]
    lines += [f"- {query}" for query in card.search_queries]
    lines += ["", "## Для менеджера", "", card.commercial.audience, ""]
    lines += [f"- {task}" for task in card.commercial.tasks]
    if result.missing_data:
        lines += ["", "## Уточнить", ""]
        lines += [f"- {item}" for item in result.missing_data]
    if result.warnings:
        lines += ["", "## Проверить вручную", ""]
        lines += [f"- {item}" for item in result.warnings]
    return "\n".join(lines) + "\n"
