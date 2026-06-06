"""
Catalog helpers for BurgerPrintsAgent.

These helpers normalize product records and provide a canonical view that can be
used by the graph, validation gate, and API serializers.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple

from agent.services.html_parser import normalize_product


SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-]{1,63}$")


def canonicalize_short_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    return text


def is_valid_short_code(value: Any) -> bool:
    code = canonicalize_short_code(value)
    return bool(code and SKU_PATTERN.match(code))


def _unwrap_product_payload(product: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(product, dict):
        return {}

    data = product.get("data")
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, dict):
            return nested
        return data

    return product


def extract_product_identifier(product: Dict[str, Any]) -> str:
    if not isinstance(product, dict):
        return ""

    for key in ("short_code", "shortCode", "sku", "id", "product_id"):
        code = canonicalize_short_code(product.get(key))
        if code:
            return code
    return ""


def normalize_catalog_product(product: Dict[str, Any]) -> Dict[str, Any]:
    raw = _unwrap_product_payload(product)
    normalized = normalize_product(raw)
    short_code = canonicalize_short_code(
        normalized.get("short_code") or raw.get("short_code") or raw.get("shortCode")
    )
    normalized["id"] = short_code or normalized.get("id", "")
    normalized["short_code"] = short_code or normalized.get("short_code", "")
    normalized["sku_valid"] = is_valid_short_code(short_code)
    normalized["inventory_status"] = normalized.get("inventory_status", "unknown")
    normalized["source_verified"] = "catalog"
    return normalized


def normalize_catalog_products(products: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for product in products or []:
        if not isinstance(product, dict):
            continue
        item = normalize_catalog_product(product)
        if item.get("short_code"):
            normalized.append(item)
    return normalized


def build_catalog_index(products: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_products = normalize_catalog_products(products)
    by_short_code = {
        p["short_code"]: p
        for p in normalized_products
        if is_valid_short_code(p.get("short_code"))
    }
    by_name = {
        canonicalize_short_code(p.get("name", "")): p
        for p in normalized_products
        if p.get("name")
    }
    return {
        "products_norm": normalized_products,
        "by_short_code": by_short_code,
        "by_name": by_name,
        "count": len(normalized_products),
    }


def extract_out_of_stock_ids(payload: Any) -> List[str]:
    if isinstance(payload, dict):
        items = payload.get("data", payload.get("result", []))
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    ids: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = canonicalize_short_code(
            item.get("short_code")
            or item.get("shortCode")
            or item.get("sku")
            or item.get("id")
        )
        if code:
            ids.append(code)
    return sorted(set(ids))


def annotate_inventory(products: Iterable[Dict[str, Any]], out_of_stock_ids: Iterable[str]) -> List[Dict[str, Any]]:
    out_of_stock = {canonicalize_short_code(x) for x in out_of_stock_ids or []}
    annotated: List[Dict[str, Any]] = []
    for product in products or []:
        if not isinstance(product, dict):
            continue
        item = deepcopy(product)
        code = canonicalize_short_code(item.get("short_code") or item.get("id"))
        if not code:
            item["inventory_status"] = "unknown"
        elif code in out_of_stock:
            item["inventory_status"] = "out_of_stock"
        else:
            item["inventory_status"] = "available"
        item["short_code"] = code or item.get("short_code", "")
        item["id"] = code or item.get("id", "")
        item["sku_valid"] = is_valid_short_code(code)
        annotated.append(item)
    return annotated


def validate_product_list(products: Iterable[Dict[str, Any]], catalog_index: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return a sanitized product list plus a list of validation errors."""
    index = catalog_index or {}
    by_short_code = index.get("by_short_code", {}) or {}
    sanitized: List[Dict[str, Any]] = []
    errors: List[str] = []

    for product in products or []:
        if not isinstance(product, dict):
            continue
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if not code or code not in by_short_code:
            errors.append(f"Unknown product identifier: {product.get('short_code') or product.get('id') or '?'}")
            continue
        sanitized.append(deepcopy(by_short_code[code]))

    return sanitized, errors

