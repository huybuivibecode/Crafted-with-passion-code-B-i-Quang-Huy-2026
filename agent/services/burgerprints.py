"""
BurgerPrints API service - async httpx client
Wraps all /v2 endpoints used by the agent
"""
import os
import httpx
from django.conf import settings

BASE_URL = "https://api.burgerprints.com"


def _get_headers() -> dict:
    api_key = getattr(settings, "BURGER_PRINTS_API_KEY", "") or os.getenv("BURGER_PRINTS_API_KEY", "")
    return {
        "api-key": api_key,          # BurgerPrints yêu cầu header "api-key" (chữ thường)
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_products(page: int = 1, limit: int = 100) -> list:
    """
    GET /v2/product - Lấy danh sách sản phẩm
    Returns: list of product dicts (data.result)
    """
    all_products = []
    current_page = 1
    page_size = min(limit, 100)

    with httpx.Client(timeout=60) as client:
        while len(all_products) < limit:
            resp = client.get(
                f"{BASE_URL}/v2/product",
                headers=_get_headers(),
                params={"page": current_page, "pageSize": page_size},
            )
            resp.raise_for_status()
            body = resp.json()

            # Format: {code, message, data: {total, page, pageSize, result: [...]}}
            data = body.get("data", {})
            result = data.get("result", [])
            if not result:
                break

            all_products.extend(result)
            total = data.get("total", 0)
            if len(all_products) >= total or len(all_products) >= limit:
                break
            current_page += 1

    return all_products[:limit]


def get_product_detail(short_code: str) -> dict:
    """GET /v2/product/{short_code} - Chi tiết sản phẩm theo short_code"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/product/{short_code}",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        # Có thể trả về {data: {...}} hoặc trực tiếp object
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body


def get_out_of_stock() -> list:
    """GET /v2/product/out-of-stock - Sản phẩm hết hàng"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/product/out-of-stock",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict):
            return body.get("data", body.get("result", []))
        return body if isinstance(body, list) else []


def create_order(payload: dict) -> dict:
    """POST /v2/order - Tạo đơn hàng mới"""
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{BASE_URL}/v2/order",
            headers=_get_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def get_orders(page: int = 1, limit: int = 20) -> dict:
    """GET /v2/order - Danh sách đơn hàng"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/order",
            headers=_get_headers(),
            params={"page": page, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()


def get_order_detail(order_id: str) -> dict:
    """GET /v2/order/{id} - Chi tiết đơn hàng"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/order/{order_id}",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()


def get_balance() -> dict:
    """GET /v2/balance - Số dư tài khoản"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/balance",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
