"""
BurgerPrints API v2 - Full Data Fetcher
Gọi tất cả endpoint, paginate đầy đủ, lưu JSON vào datajson/
"""
import os
import sys
import json
import time
import httpx

# ── Config ──
sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://api.burgerprints.com"
API_KEY = os.getenv("BURGER_PRINTS_API_KEY", "")

# Load from .env if not set
if not API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("BURGER_PRINTS_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

HEADERS = {
    "api-key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "datajson")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_json(filename, data):
    """Lưu data ra file JSON"""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(path)
    print(f"  💾 Saved: {filename} ({size:,} bytes)")
    return path


def fetch_paginated(endpoint, page_size=100, max_pages=100):
    """Fetch tất cả pages từ 1 endpoint có pagination"""
    all_results = []
    page = 1
    total = None

    with httpx.Client(timeout=60) as client:
        while page <= max_pages:
            print(f"    📄 Page {page}...", end=" ")
            resp = client.get(
                f"{BASE_URL}{endpoint}",
                headers=HEADERS,
                params={"page": page, "pageSize": page_size},
            )

            if resp.status_code != 200:
                print(f"❌ Status {resp.status_code}: {resp.text[:100]}")
                break

            body = resp.json()
            
            # Format 1 (Product/Out of stock): {"code": 200, "data": {"total": 500, "result": [...]}}
            # Format 2 (Order): {"total": 0, "data": [...]}
            
            result = []
            current_total = 0
            
            if "code" in body and isinstance(body.get("data"), dict):
                # Format 1
                data_obj = body["data"]
                current_total = data_obj.get("total", 0)
                result = data_obj.get("result", [])
            elif isinstance(body.get("data"), list):
                # Format 2
                current_total = body.get("total", 0)
                result = body["data"]
            else:
                print(f"❌ Unknown response format: {str(body)[:100]}")
                break

            if total is None:
                total = current_total
                print(f"(total={total})", end=" ")

            if not result:
                print("(empty page, done)")
                break

            all_results.extend(result)
            print(f"+{len(result)} items (cumulative: {len(all_results)})")

            if len(all_results) >= total:
                break

            page += 1
            time.sleep(0.3)  # Rate limiting

    return all_results, total


def main():
    print("=" * 60)
    print("🍔 BurgerPrints API v2 - Full Data Fetcher")
    print(f"   API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"   Output:  {OUTPUT_DIR}")
    print("=" * 60)

    # ─────────────────────────────────────────────────
    # 1. GET /v2/authenticated
    # ─────────────────────────────────────────────────
    print("\n[1/6] 🔐 GET /v2/authenticated")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{BASE_URL}/v2/authenticated", headers=HEADERS)
            auth_data = resp.json()
            print(f"  Status: {resp.status_code}")
            print(f"  Result: {json.dumps(auth_data, ensure_ascii=False)}")
            save_json("authenticated.json", auth_data)
    except Exception as e:
        print(f"  ❌ Error: {e}")
        save_json("authenticated.json", {"error": str(e)})

    # ─────────────────────────────────────────────────
    # 2. GET /v2/product (ALL pages)
    # ─────────────────────────────────────────────────
    print("\n[2/6] 📦 GET /v2/product (all pages)")
    try:
        products, total = fetch_paginated("/v2/product", page_size=100)
        print(f"  ✅ Total fetched: {len(products)} / {total} products")
        save_json("products.json", {
            "total": total,
            "fetched": len(products),
            "result": products,
        })
    except Exception as e:
        print(f"  ❌ Error: {e}")
        products = []
        save_json("products.json", {"error": str(e)})

    # ─────────────────────────────────────────────────
    # 3. GET /v2/product/{short_code} for each product
    # ─────────────────────────────────────────────────
    print(f"\n[3/6] 🔍 GET /v2/product/{{short_code}} (detail for each)")
    product_details = []
    short_codes = list({p.get("short_code", "") for p in products if p.get("short_code")})
    print(f"  Found {len(short_codes)} unique short_codes")

    with httpx.Client(timeout=30) as client:
        for i, sc in enumerate(short_codes):
            try:
                resp = client.get(
                    f"{BASE_URL}/v2/product/{sc}",
                    headers=HEADERS,
                )
                if resp.status_code == 200:
                    detail = resp.json()
                    product_details.append({
                        "short_code": sc,
                        "status": resp.status_code,
                        "data": detail,
                    })
                    if (i + 1) % 20 == 0 or i == 0:
                        print(f"    ✅ [{i+1}/{len(short_codes)}] {sc}")
                else:
                    product_details.append({
                        "short_code": sc,
                        "status": resp.status_code,
                        "error": resp.text[:200],
                    })
                    print(f"    ❌ [{i+1}/{len(short_codes)}] {sc} -> {resp.status_code}")

                time.sleep(0.2)  # Rate limiting
            except Exception as e:
                product_details.append({
                    "short_code": sc,
                    "status": 0,
                    "error": str(e),
                })
                print(f"    ❌ [{i+1}/{len(short_codes)}] {sc} -> {e}")

    print(f"  ✅ Total details fetched: {len(product_details)}")
    save_json("product_details.json", {
        "total": len(product_details),
        "result": product_details,
    })

    # ─────────────────────────────────────────────────
    # 4. GET /v2/product/outofstock (ALL pages)
    # ─────────────────────────────────────────────────
    print("\n[4/6] 🚫 GET /v2/product/outofstock (all pages)")
    try:
        oos_items, oos_total = fetch_paginated("/v2/product/outofstock", page_size=100)
        print(f"  ✅ Total fetched: {len(oos_items)} / {oos_total} out-of-stock entries")
        save_json("outofstock.json", {
            "total": oos_total,
            "fetched": len(oos_items),
            "result": oos_items,
        })
    except Exception as e:
        print(f"  ❌ Error: {e}")
        save_json("outofstock.json", {"error": str(e)})

    # ─────────────────────────────────────────────────
    # 5. GET /v2/order (ALL pages)
    # ─────────────────────────────────────────────────
    print("\n[5/6] 📋 GET /v2/order (all pages)")
    try:
        orders, orders_total = fetch_paginated("/v2/order", page_size=100)
        print(f"  ✅ Total fetched: {len(orders)} / {orders_total} orders")
        save_json("orders.json", {
            "total": orders_total,
            "fetched": len(orders),
            "result": orders,
        })

        # Fetch detail for each order (if any)
        if orders:
            print(f"\n  📋 Fetching order details for {len(orders)} orders...")
            order_details = []
            with httpx.Client(timeout=30) as client:
                for i, order in enumerate(orders):
                    oid = order.get("id", order.get("order_id", ""))
                    if not oid:
                        continue
                    try:
                        resp = client.get(
                            f"{BASE_URL}/v2/order/{oid}",
                            headers=HEADERS,
                        )
                        order_details.append({
                            "order_id": oid,
                            "status": resp.status_code,
                            "data": resp.json() if resp.status_code == 200 else resp.text[:200],
                        })
                        if (i + 1) % 10 == 0:
                            print(f"    ✅ [{i+1}/{len(orders)}]")
                        time.sleep(0.2)
                    except Exception as e:
                        order_details.append({"order_id": oid, "error": str(e)})
            save_json("order_details.json", {
                "total": len(order_details),
                "result": order_details,
            })

    except Exception as e:
        print(f"  ❌ Error: {e}")
        save_json("orders.json", {"error": str(e)})

    # ─────────────────────────────────────────────────
    # 6. GET /v2/balance
    # ─────────────────────────────────────────────────
    print("\n[6/6] 💰 GET /v2/balance")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{BASE_URL}/v2/balance", headers=HEADERS)
            balance_data = resp.json() if resp.status_code == 200 else {
                "status": resp.status_code,
                "body": resp.text[:500],
            }
            print(f"  Status: {resp.status_code}")
            print(f"  Result: {json.dumps(balance_data, ensure_ascii=False)[:200]}")
            save_json("balance.json", balance_data)
    except Exception as e:
        print(f"  ❌ Error: {e}")
        save_json("balance.json", {"error": str(e)})

    # ─────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    files = os.listdir(OUTPUT_DIR)
    total_size = 0
    for f in sorted(files):
        fp = os.path.join(OUTPUT_DIR, f)
        sz = os.path.getsize(fp)
        total_size += sz
        print(f"  📄 {f:30s} {sz:>10,} bytes")
    print(f"  {'─' * 42}")
    print(f"  {'Total':30s} {total_size:>10,} bytes")
    print(f"  📁 Output dir: {OUTPUT_DIR}")
    print("✅ Done!")


if __name__ == "__main__":
    main()
