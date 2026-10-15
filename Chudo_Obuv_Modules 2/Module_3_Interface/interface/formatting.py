"""Общее оформление текста и значений."""

from string import Formatter
from decimal import Decimal

from design import (
    CURRENCY,
    FONT_FAMILY,
    FONT_SIZES,
    QUANTITY_UNIT,
    TEXTS,
    VARIANT_LABEL,
)


def font(role="body", bold=False):
    value = (FONT_FAMILY, FONT_SIZES[role])
    return value + ("bold",) if bold else value


def money(value):
    return f"{value:,.2f} {CURRENCY}".replace(",", " ").strip()


def render(template, values):
    """Подставляем значения в простые шаблоны {поле}."""
    parts = []
    for literal, field, spec, conversion in Formatter().parse(template):
        parts.append(literal)
        if field is None:
            continue
        if not field.isidentifier() or spec or conversion:
            raise ValueError(
                f"Используй простой шаблон {{поле}}, без выражений: {template}"
            )
        value = values.get(field)
        parts.append("—" if value is None or value == "" else str(value))
    return "".join(parts)


def text(key, **values):
    template = TEXTS[key]
    if key in {"item_variant", "item_edit"} and values.get("value") in (
        None,
        "",
        "None",
    ):
        template = template.replace(", {variant} {value}", "").replace(
            "{variant} {value}", ""
        )
    return render(template, {"unit": QUANTITY_UNIT, "variant": VARIANT_LABEL, **values})


def product_context(product, price, discount=None):
    original = Decimal(
        str(discount["original_price"] if discount else product.get("price", price))
    )
    final = Decimal(str(price))
    percent = (
        Decimal(str(discount["percent"]))
        if discount
        else ((original - final) * 100 / original if original > 0 else Decimal("0"))
    )
    applied = bool(discount["applied"]) if discount else final < original
    return {
        **product,
        "unit": QUANTITY_UNIT,
        "variant": VARIANT_LABEL,
        "price_text": money(price),
        "original_price_text": money(original),
        "discount_applied": applied,
        "discount_text": (
            "Скидка −" + format(percent.normalize(), "f") + "%" if applied else ""
        ),
        "discount_reason": discount["reason"] if discount else "",
    }


def field_rows(specifications, values, layout=None):
    for spec in specifications:
        if (
            "{total_quantity}" in spec.get("template", "")
            and values.get("total_quantity") is None
        ):
            continue
        if spec.get("layout") and spec["layout"] != layout:
            continue
        fields = spec.get("fields", ())
        if (
            spec.get("hide_empty")
            and fields
            and all(values.get(f) in (None, "") for f in fields)
        ):
            continue
        yield render(spec["template"], values), spec.get("style", "normal")
