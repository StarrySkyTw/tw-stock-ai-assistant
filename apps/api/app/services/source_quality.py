from __future__ import annotations

from typing import Any

TRUSTED_FUNDAMENTAL_SOURCES = ("finmind", "twse-openapi", "tpex-openapi")
TRUSTED_INSTITUTIONAL_SOURCES = ("finmind", "twse-t86", "tpex-insti")
TRUSTED_MARGIN_SOURCES = ("finmind", "twse-margin", "tpex-margin")
TRUSTED_PRICE_SOURCES = ("finmind", "twse", "yahoo")
TRUSTED_SHAREHOLDING_SOURCES = ("finmind", "tdcc")
TRUSTED_NEWS_SOURCES = ("finmind", "twse-material", "tpex-material")


def normalize_source(source: Any) -> str:
    return str(source or "").strip().lower()


def is_sample_source(source: Any) -> bool:
    normalized = normalize_source(source)
    return not normalized or "sample" in normalized


def is_unavailable_source(source: Any) -> bool:
    normalized = normalize_source(source)
    return not normalized or normalized == "unavailable"


def is_trusted_source(source: Any, kind: str) -> bool:
    normalized = normalize_source(source)
    if not normalized or "sample" in normalized or normalized == "unavailable":
        return False

    if kind == "fundamental":
        return any(item in normalized for item in TRUSTED_FUNDAMENTAL_SOURCES)
    if kind == "institutional":
        return any(item in normalized for item in TRUSTED_INSTITUTIONAL_SOURCES)
    if kind == "margin":
        return any(item in normalized for item in TRUSTED_MARGIN_SOURCES)
    if kind == "price":
        return any(item in normalized for item in TRUSTED_PRICE_SOURCES)
    if kind == "shareholding":
        return any(item in normalized for item in TRUSTED_SHAREHOLDING_SOURCES)
    if kind == "news":
        return any(item in normalized for item in TRUSTED_NEWS_SOURCES)
    return False


def has_trusted_fundamental(sources: dict[str, str]) -> bool:
    return is_trusted_source(sources.get("fundamental"), "fundamental")


def has_trusted_price(sources: dict[str, str]) -> bool:
    return is_trusted_source(sources.get("price"), "price")
