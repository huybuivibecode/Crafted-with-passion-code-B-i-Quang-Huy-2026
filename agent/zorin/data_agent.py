from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.services import burgerprints as bp_api
from agent.services.catalog_store import build_catalog_index, extract_out_of_stock_ids
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
            return (s or "").lower().replace(" ", "").replace("-", "")

        wanted = [_clean(x) for x in (product_names or []) if x]
        for product in products_raw:
            name = (product.get("name", "") or product.get("shortCodeName", "") or "")
            sku = product.get("short_code") or product.get("shortCode") or ""
            name_clean = _clean(name)
            sku_clean = _clean(sku)
            for token in wanted:
                if not token:
                    continue
                if token in name_clean or token in sku_clean or (sku_clean and sku_clean in token):
                    try:
                        detail = bp_api.get_product_detail(sku)
                        payload = detail if isinstance(detail, dict) and detail else product
                        compare_products.append(normalize_product(payload))
                    except Exception:
                        compare_products.append(normalize_product(product))
                    break

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
            variations = detail.get("variations", []) if isinstance(detail, dict) else []
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
