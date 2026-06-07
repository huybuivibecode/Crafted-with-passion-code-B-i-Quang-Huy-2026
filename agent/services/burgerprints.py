"""
BurgerPrints API service - sync httpx client
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


# ---------------------------------------------------------------------------
# Product endpoints
# ---------------------------------------------------------------------------

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
    """GET /v2/product/out-of-stock - Sản phẩm hết hàng

    BurgerPrints API có thể expose endpoint là `/v2/product/outofstock` (không dấu gạch).
    Hàm này thử cả hai để tránh lỗi 400/404 tùy môi trường.
    """
    with httpx.Client(timeout=30) as client:
        last_exc = None
        for path in ("/v2/product/out-of-stock", "/v2/product/outofstock"):
            try:
                resp = client.get(
                    f"{BASE_URL}{path}",
                    headers=_get_headers(),
                )
                resp.raise_for_status()
                body = resp.json()
                if isinstance(body, dict):
                    return body.get("data", body.get("result", []))
                return body if isinstance(body, list) else []
            except httpx.HTTPStatusError as e:
                last_exc = e
                status_code = e.response.status_code if e.response is not None else None
                if status_code not in (400, 404):
                    raise
                continue
        if last_exc:
            raise last_exc
        return []


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------

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


def cancel_order(order_id: str) -> dict:
    """PUT /v2/order/cancel - Huỷ đơn hàng"""
    with httpx.Client(timeout=30) as client:
        resp = client.put(
            f"{BASE_URL}/v2/order/cancel",
            headers=_get_headers(),
            json={"id": order_id},
        )
        resp.raise_for_status()
        return resp.json()


def get_order_tracking(order_id: str) -> dict:
    """GET /v2/order/tracking - Theo dõi đơn hàng"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/order/tracking",
            headers=_get_headers(),
            params={"id": order_id},
        )
        resp.raise_for_status()
        return resp.json()


def charge_order(order_ids: list) -> dict:
    """POST /v2/order/charge - Thanh toán đơn hàng
    
    Args:
        order_ids: list of order ID strings to charge
    """
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{BASE_URL}/v2/order/charge",
            headers=_get_headers(),
            json={"order_ids": order_ids if isinstance(order_ids, list) else [order_ids]},
        )
        resp.raise_for_status()
        return resp.json()


def delete_order(order_id: str) -> dict:
    """DELETE /v2/order/{id} - Xóa đơn hàng (chỉ được khi order ở trạng thái unpaid)"""
    with httpx.Client(timeout=30) as client:
        resp = client.delete(
            f"{BASE_URL}/v2/order/{order_id}",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------

def get_authenticated() -> dict:
    """GET /v2/authenticated - Kiểm tra API key hợp lệ"""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{BASE_URL}/v2/authenticated",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)


def get_balance() -> dict:
    """GET /v2/balance - Số dư tài khoản"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{BASE_URL}/v2/balance",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
