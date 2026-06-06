"""
Catalog Cache - In-memory cache cho BurgerPrints product catalog
TTL: 5 phút (cấu hình qua settings.CATALOG_CACHE_TTL)
Thread-safe với threading.Lock
"""
import time
import threading
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache store
# ---------------------------------------------------------------------------

_lock = threading.Lock()

_catalog_cache = {
    "products_raw": [],
    "timestamp": 0.0,
}

_oos_cache = {
    "out_of_stock_ids": [],
    "timestamp": 0.0,
}


def _get_ttl() -> float:
    """TTL tính bằng giây, mặc định 5 phút."""
    return float(getattr(settings, "CATALOG_CACHE_TTL", 300))


# ---------------------------------------------------------------------------
# Products catalog cache
# ---------------------------------------------------------------------------

def get_cached_products() -> Optional[list]:
    """
    Trả về cached product list nếu còn hợp lệ (TTL chưa hết).
    Returns None nếu cache đã hết hạn hoặc chưa có.
    """
    with _lock:
        age = time.time() - _catalog_cache["timestamp"]
        ttl = _get_ttl()
        if _catalog_cache["products_raw"] and age < ttl:
            logger.debug(f"[CatalogCache] HIT - {len(_catalog_cache['products_raw'])} products, age={age:.0f}s")
            return list(_catalog_cache["products_raw"])
        return None


def set_cached_products(products: list) -> None:
    """Lưu product list vào cache."""
    with _lock:
        _catalog_cache["products_raw"] = list(products)
        _catalog_cache["timestamp"] = time.time()
        logger.info(f"[CatalogCache] SET - {len(products)} products cached")


def invalidate_products_cache() -> None:
    """Xoá cache sản phẩm (dùng khi có trigger thủ công)."""
    with _lock:
        _catalog_cache["products_raw"] = []
        _catalog_cache["timestamp"] = 0.0
        logger.info("[CatalogCache] INVALIDATED products cache")


# ---------------------------------------------------------------------------
# Out-of-stock cache
# ---------------------------------------------------------------------------

def get_cached_oos() -> Optional[list]:
    """
    Trả về cached out-of-stock IDs nếu còn hợp lệ.
    OOS cache TTL ngắn hơn: 2 phút.
    """
    with _lock:
        oos_ttl = min(_get_ttl(), 120.0)  # max 2 phút cho OOS
        age = time.time() - _oos_cache["timestamp"]
        if _oos_cache["out_of_stock_ids"] is not None and age < oos_ttl:
            logger.debug(f"[OOSCache] HIT - {len(_oos_cache['out_of_stock_ids'])} OOS items, age={age:.0f}s")
            return list(_oos_cache["out_of_stock_ids"])
        return None


def set_cached_oos(oos_ids: list) -> None:
    """Lưu out-of-stock IDs vào cache."""
    with _lock:
        _oos_cache["out_of_stock_ids"] = list(oos_ids)
        _oos_cache["timestamp"] = time.time()
        logger.info(f"[OOSCache] SET - {len(oos_ids)} OOS items cached")


def invalidate_oos_cache() -> None:
    """Xoá cache OOS."""
    with _lock:
        _oos_cache["out_of_stock_ids"] = []
        _oos_cache["timestamp"] = 0.0
        logger.info("[OOSCache] INVALIDATED OOS cache")


# ---------------------------------------------------------------------------
# Cache stats
# ---------------------------------------------------------------------------

def get_cache_stats() -> dict:
    """Trả về thông tin trạng thái cache."""
    with _lock:
        ttl = _get_ttl()
        products_age = time.time() - _catalog_cache["timestamp"]
        oos_age = time.time() - _oos_cache["timestamp"]
        return {
            "products": {
                "count": len(_catalog_cache["products_raw"]),
                "age_seconds": round(products_age),
                "ttl_seconds": round(ttl),
                "valid": bool(_catalog_cache["products_raw"]) and products_age < ttl,
            },
            "out_of_stock": {
                "count": len(_oos_cache["out_of_stock_ids"]),
                "age_seconds": round(oos_age),
                "ttl_seconds": 120,
                "valid": oos_age < 120.0,
            },
        }
