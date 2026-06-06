from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.services import burgerprints as bp_api
from agent.services.catalog_store import build_catalog_index, extract_out_of_stock_ids, normalize_catalog_product
from agent.services.html_parser import normalize_product
from agent.services.catalog_cache import (
    get_cached_products,
    set_cached_products,
    get_cached_oos,
    set_cached_oos,
)

logger = logging.getLogger(__name__)


class DataAgent:
    def fetch_catalog(self, limit: int = 500) -> Dict[str, Any]:
        """
        Lấy catalog sản phẩm. Sử dụng in-memory cache để tránh gọi API lặp lại.
        Cache TTL: 5 phút (cấu hình qua settings.CATALOG_CACHE_TTL).
        """
        products_raw = get_cached_products()
        if products_raw is None:
            logger.info("[DataAgent] Cache MISS - fetching from BurgerPrints API...")
            products_raw = bp_api.get_products(limit=limit)
            set_cached_products(products_raw)
        else:
            logger.info(f"[DataAgent] Cache HIT - {len(products_raw)} products")

        catalog_index = build_catalog_index(products_raw)
        products_norm = catalog_index.get("products_norm", [])
        return {
            "products_raw": products_raw,
            "products_norm": products_norm,
            "catalog_index": catalog_index,
        }

    def fetch_out_of_stock(self) -> Dict[str, Any]:
        """
        Lấy danh sách sản phẩm hết hàng. Cache TTL: 2 phút.
        """
        out_of_stock_ids = get_cached_oos()
        if out_of_stock_ids is None:
            logger.info("[DataAgent] OOS Cache MISS - fetching...")
            try:
                data = bp_api.get_out_of_stock()
                out_of_stock_ids = extract_out_of_stock_ids(data)
                set_cached_oos(out_of_stock_ids)
            except Exception as e:
                logger.warning(f"[DataAgent] OOS fetch failed: {e}")
                out_of_stock_ids = []
        else:
            logger.info(f"[DataAgent] OOS Cache HIT - {len(out_of_stock_ids)} items")

        return {
            "out_of_stock_ids": out_of_stock_ids,
            "inventory_snapshot": {
                "out_of_stock_ids": out_of_stock_ids,
                "source": "burgerprints:v2/product/out-of-stock",
                "count": len(out_of_stock_ids),
            },
        }

    def fetch_compare_products(self, product_names: List[str], limit: int = 500) -> Dict[str, Any]:
        """
        Lấy chi tiết sản phẩm để so sánh. Tận dụng catalog cache.
        """
        catalog = self.fetch_catalog(limit=limit)
        products_raw = catalog.get("products_raw", [])
        compare_products: List[dict] = []

        def _clean(s: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

        wanted_raw = [x for x in (product_names or []) if x]
        wanted = [_clean(x) for x in wanted_raw if x]

        selected_skus: List[str] = []

        for idx, token in enumerate(wanted):
            best = None
            best_score = -10**9
            raw_token = (wanted_raw[idx] or "").lower()
            want_kid = any(x in raw_token for x in ["kid", "kids", "youth", "toddler", "baby"])
            want_women = any(x in raw_token for x in ["women", "woman", "lady", "ladies"])

            for product in products_raw:
                name = (product.get("name", "") or product.get("shortCodeName", "") or "")
                sku = product.get("short_code") or product.get("shortCode") or ""
                name_clean = _clean(name)
                sku_clean = _clean(sku)

                if not token:
                    continue

                score = 0
                if sku_clean and token == sku_clean:
                    score += 1000
                if sku_clean and (token in sku_clean or sku_clean in token):
                    score += 600
                if token in name_clean:
                    score += 450
                if name_clean.startswith(token):
                    score += 60

                name_lower = (name or "").lower()
                if any(x in name_lower for x in ["kid", "kids", "youth", "toddler", "baby"]) and not want_kid:
                    score -= 250
                if any(x in name_lower for x in ["women", "woman", "lady", "ladies"]) and not want_women:
                    score -= 80

                if score > best_score:
                    best_score = score
                    best = product

            if best and best_score >= 400:
                sku = best.get("short_code") or best.get("shortCode") or ""
                if sku and sku not in selected_skus:
                    selected_skus.append(sku)

        if selected_skus:
            for sku in selected_skus[:4]:
                try:
                    detail = bp_api.get_product_detail(sku)
                    compare_products.append(normalize_catalog_product(detail))
                except Exception:
                    fallback = next((p for p in products_raw if (p.get("short_code") or p.get("shortCode")) == sku), None)
                    if fallback:
                        compare_products.append(normalize_product(fallback))

        if not compare_products and products_raw:
            compare_products = [normalize_product(p) for p in products_raw[:3]]

        return {
            **catalog,
            "compare_products": compare_products,
        }

    def fetch_filtered_variations(
        self,
        product_short_code: str,
        partner: Optional[str] = None,
        color: Optional[str] = None,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Lấy variations của một sản phẩm và lọc theo partner/color/price."""
        try:
            detail = bp_api.get_product_detail(product_short_code)
            variations = (normalize_catalog_product(detail) or {}).get("variations", [])
            filtered = []
            for v in variations:
                if partner and v.get("partner_name", "").lower() != partner.lower():
                    continue
                if color and v.get("color", "").lower() != color.lower():
                    continue
                price = v.get("price", 0.0)
                if max_price is not None and price > max_price:
                    continue
                if min_price is not None and price < min_price:
                    continue
                filtered.append(v)
            return filtered
        except Exception:
            return []
