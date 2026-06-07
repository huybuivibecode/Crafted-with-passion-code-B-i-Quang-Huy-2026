"""
Shared BurgerPrints API knowledge derived from BurgerPrintAPI.md.

The goal is to give every LLM-backed helper the same source of truth about
endpoints, response shapes, and high-signal field names without hardcoding a
separate prompt summary in each module.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parents[2]
API_DOC_PATH = BASE_DIR / "BurgerPrintAPI.md"


def _clean_excerpt(text: str) -> str:
    cleaned = re.sub(r"\r\n?", "\n", text or "")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_lines(lines: list[str], pattern: str, radius: int = 8) -> str:
    regex = re.compile(pattern, re.IGNORECASE)
    for idx, line in enumerate(lines):
        if regex.search(line):
            start = max(0, idx - radius)
            end = min(len(lines), idx + radius + 1)
            excerpt = "\n".join(lines[start:end])
            return _clean_excerpt(excerpt)
    return ""


@lru_cache(maxsize=1)
def get_api_knowledge() -> str:
    fallback = """
BURGERPRINTS API V2.0 - SHARED KNOWLEDGE

Authentication:
- All requests use HTTPS.
- Header required: api-key.
- API health endpoint: GET /v2/authenticated.

Product and catalog endpoints:
- GET /v2/product: paginated catalog listing. Common pagination params in the doc are page / page_size, while the current integration also uses pageSize.
- GET /v2/product/{short_code}: product detail / variant data.
- GET /v2/product/out-of-stock or /v2/product/outofstock: out-of-stock product list.

Order endpoints:
- GET /v2/order: list orders.
- GET /v2/order/{id}: order detail.
- POST /v2/order: create order.
- PUT /v2/order/cancel: cancel order.
- GET /v2/order/tracking and POST /v2/order/charge are also documented.

High-signal fields seen in the doc and current integration:
- Product identity: short_code, sku, base_short_code, id, product_id.
- Variant attributes: color_name / color_value, size_name, sku, short_code, quantity.
- Pricing fields: price, base_cost, amount, sub_amount, shipping_fee, currency.
- Order shipping: shipping.address.country, state, city, postal_code.
- Availability / state: status, state, payment_state, fulfill_state.

Behavior rules for agents:
- Never invent SKU, partner, market, price, shipping, or stock data.
- Product recommendation must satisfy hard constraints first, then score/rank.
- Stock checking must match the requested product and requested market/location.
- Partner/factory comparison should focus on data-backed fields such as color count, location/market fit, price range, processing/shipping constraints, and available variants.
""".strip()

    if not API_DOC_PATH.exists():
        return fallback

    try:
        raw = API_DOC_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return fallback

    lines = raw.splitlines()
    authenticated = _extract_lines(lines, r"/v2/authenticated")
    orders = _extract_lines(lines, r"https://api\.burgerprints\.com/v2/order$")
    order_detail = _extract_lines(lines, r"/v2/order/\{id\}")
    base_short_code = _extract_lines(lines, r"base_short_code")
    short_code = _extract_lines(lines, r"short_code")
    shipping_fee = _extract_lines(lines, r"shipping_fee")

    excerpts = [section for section in [authenticated, orders, order_detail, base_short_code, short_code, shipping_fee] if section]
    if not excerpts:
        return fallback

    header = (
        "BURGERPRINTS API V2.0 - KNOWLEDGE DERIVED FROM BurgerPrintAPI.md\n\n"
        "Use this as the canonical prompt context for endpoint semantics, request fields, and response fields.\n"
        "When the doc and runtime wrappers differ slightly on pagination naming, prefer the real API fields but do not invent unsupported parameters.\n"
    )
    guidance = """

Operational guidance:
- Authentication uses HTTPS and api-key header.
- For product recommendation: call catalog data, apply hard constraints first, then score/rank and explain.
- For stock checking: verify the exact requested product/SKU and the requested market/location.
- For partner/factory comparison: compare on supported colors, variant/SKU coverage, price range, and fulfillment location/lead-time when available.
- Preserve exact field names when reasoning about API payloads: short_code, sku, base_short_code, color_name, size_name, price, base_cost, shipping_fee, state, status, shipping.address.country.
""".strip()

    return _clean_excerpt(header + "\n\n".join(excerpts) + "\n\n" + guidance)
