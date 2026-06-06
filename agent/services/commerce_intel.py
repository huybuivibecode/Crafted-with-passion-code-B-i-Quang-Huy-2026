"""
Deterministic commerce intelligence helpers.

This module contains rule-based proxies for market, season, weather, trend,
competition, review, persona, compatibility, pricing, and profit analysis.
External data providers can later replace these functions without changing the
LangGraph topology.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List


SCORING_WEIGHTS = {
    "trend": 0.18,
    "market_fit": 0.18,
    "season_fit": 0.14,
    "weather_fit": 0.10,
    "inventory": 0.12,
    "margin": 0.12,
    "review": 0.04,
    "compatibility": 0.06,
    "persona": 0.04,
    "competition": 0.02,
}


MARKET_PROFILES = {
    "US": {
        "market": "USA",
        "preferred_categories": ["tshirt", "tanktop", "mug", "tote"],
        "avg_price": 29,
        "competition": "medium",
        "personas": ["Gen Z", "Millennials", "Pet Lovers", "Fitness Enthusiasts"],
    },
    "EU": {
        "market": "Europe",
        "preferred_categories": ["tshirt", "sweatshirt", "mug", "poster"],
        "avg_price": 31,
        "competition": "medium",
        "personas": ["Millennials", "Minimalist Buyers", "Gift Shoppers"],
    },
    "GERMANY": {
        "market": "Germany",
        "preferred_categories": ["tshirt", "sweatshirt", "hoodie"],
        "avg_price": 32,
        "competition": "medium",
        "personas": ["Quality-focused Buyers", "Millennials"],
    },
    "UK": {
        "market": "UK",
        "preferred_categories": ["tshirt", "sweatshirt", "mug"],
        "avg_price": 28,
        "competition": "medium",
        "personas": ["Gift Shoppers", "Pop Culture Buyers"],
    },
    "FRANCE": {
        "market": "France",
        "preferred_categories": ["tshirt", "tote", "poster"],
        "avg_price": 30,
        "competition": "medium",
        "personas": ["Fashion Buyers", "Gift Shoppers"],
    },
}


def infer_market(criteria: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Lấy profile thị trường dựa trên criteria đã được LLM trích xuất."""
    market_key = criteria.get("market") or criteria.get("location_preference") or "US"
    market_key = market_key.upper()

    # Map các biến thể về key chuẩn trong MARKET_PROFILES
    if market_key in ["USA", "AMERICA", "MỸ", "MY"]:
        market_key = "US"
    elif market_key in ["EUROPE", "CHÂU ÂU", "CHAU AU"]:
        market_key = "EU"
    elif market_key in ["ĐỨC", "DUC", "GERMANY"]:
        market_key = "GERMANY"

    profile = dict(MARKET_PROFILES.get(market_key, MARKET_PROFILES["US"]))
    profile["market_key"] = market_key
    profile["source"] = "LLM-driven market profile"
    return profile


def infer_category(product: Dict[str, Any]) -> str:
    text = f"{product.get('name', '')} {product.get('desc', '')}".lower()
    checks = [
        ("tanktop", ["tank top", "tanktop", "sleeveless"]),
        ("tshirt", ["t-shirt", "tee", "shirt"]),
        ("hoodie", ["hoodie", "hooded"]),
        ("sweatshirt", ["sweatshirt", "crewneck"]),
        ("longsleeve", ["long sleeve"]),
        ("mug", ["mug", "cup"]),
        ("tote", ["tote", "bag"]),
        ("poster", ["poster", "canvas"]),
        ("blanket", ["blanket"]),
        ("acrylic", ["acrylic", "plaque", "block"]),
    ]
    for category, tokens in checks:
        if any(token in text for token in tokens):
            return category
    return "other"


def infer_season(market_profile: Dict[str, Any], now: datetime | None = None) -> Dict[str, Any]:
    now = now or datetime.now()
    month = now.month
    market_key = market_profile.get("market_key", "US")
    hemisphere = "north"

    if hemisphere == "north":
        if month in (12, 1, 2):
            season = "winter"
        elif month in (3, 4, 5):
            season = "spring"
        elif month in (6, 7, 8):
            season = "summer"
        else:
            season = "fall"
    else:
        season = "summer"

    return {
        "market_key": market_key,
        "month": month,
        "season": season,
        "source": "calendar rule",
    }


def infer_weather(criteria: Dict[str, Any], market_profile: Dict[str, Any]) -> Dict[str, Any]:
    text = f"{criteria.get('summary', '')} {criteria.get('market', '')}".lower()
    city_temp = {
        "texas": 32,
        "florida": 31,
        "california": 25,
        "seattle": 18,
        "new york": 24,
        "germany": 18,
        "uk": 17,
        "france": 22,
    }
    avg_temp = None
    for key, temp in city_temp.items():
        if key in text:
            avg_temp = temp
            break
    if avg_temp is None:
        market_key = market_profile.get("market_key", "US")
        avg_temp = {"US": 27, "EU": 20, "GERMANY": 18, "UK": 17, "FRANCE": 22}.get(market_key, 24)

    return {
        "avg_temp": avg_temp,
        "source": "rule-based climate proxy",
    }


def market_fit_score(product: Dict[str, Any], market_profile: Dict[str, Any]) -> float:
    category = infer_category(product)
    preferred = market_profile.get("preferred_categories", [])
    score = 60.0
    if category in preferred:
        score += 25
    loc = (product.get("location", "") or "").upper()
    market_key = market_profile.get("market_key", "")
    if market_key == "US" and loc == "US":
        score += 15
    elif market_key in ("EU", "GERMANY", "UK", "FRANCE") and loc == "EU":
        score += 15
    elif loc not in ("", "UNKNOWN"):
        score += 5
    return clamp_score(score)


def season_fit_score(product: Dict[str, Any], season_context: Dict[str, Any]) -> float:
    category = infer_category(product)
    season = season_context.get("season", "summer")
    score = 70.0
    if season == "summer":
        if category in ("tanktop", "tshirt", "tote", "mug"):
            score += 25
        if category in ("hoodie", "sweatshirt", "blanket"):
            score -= 30
    elif season == "winter":
        if category in ("hoodie", "sweatshirt", "longsleeve", "mug", "blanket"):
            score += 25
        if category in ("tanktop",):
            score -= 35
    elif season in ("spring", "fall"):
        if category in ("tshirt", "sweatshirt", "mug", "tote"):
            score += 15
    return clamp_score(score)


def weather_fit_score(product: Dict[str, Any], weather_context: Dict[str, Any]) -> float:
    category = infer_category(product)
    avg_temp = float(weather_context.get("avg_temp", 24))
    score = 70.0
    if avg_temp >= 28:
        if category in ("tanktop", "tshirt"):
            score += 25
        if category in ("hoodie", "sweatshirt", "blanket"):
            score -= 35
    elif avg_temp <= 18:
        if category in ("hoodie", "sweatshirt", "longsleeve", "mug"):
            score += 25
        if category == "tanktop":
            score -= 25
    else:
        if category in ("tshirt", "sweatshirt", "mug", "tote"):
            score += 12
    return clamp_score(score)


def trend_score(product: Dict[str, Any], market_profile: Dict[str, Any]) -> float:
    text = f"{product.get('name', '')} {product.get('desc', '')}".lower()
    category = infer_category(product)
    score = 55.0
    if category in ("tshirt", "tanktop", "mug", "tote"):
        score += 20
    if any(token in text for token in ["vintage", "comfort colors", "bella", "canvas", "heavy cotton"]):
        score += 12
    if any(token in text for token in ["hoodie", "sweatshirt"]):
        score += 5
    return clamp_score(score)


def competition_score(product: Dict[str, Any], market_profile: Dict[str, Any]) -> float:
    category = infer_category(product)
    baseline = {
        "tshirt": 55,
        "hoodie": 62,
        "sweatshirt": 65,
        "tanktop": 72,
        "tote": 78,
        "mug": 68,
        "acrylic": 80,
        "poster": 70,
    }.get(category, 60)
    return clamp_score(float(baseline))


def review_score(product: Dict[str, Any]) -> Dict[str, Any]:
    text = f"{product.get('name', '')} {product.get('material', '')} {product.get('desc', '')}".lower()
    strengths: List[str] = []
    risks: List[str] = []
    score = 65.0
    if "100% cotton" in text or "cotton" in text:
        score += 15
        strengths.append("soft cotton feel")
    if "heavy" in text:
        score += 8
        strengths.append("durable/heavyweight fabric")
        risks.append("can feel warm in hot climates")
    if "budget" in text:
        score += 8
        strengths.append("budget-friendly entry product")
    if infer_category(product) in ("hoodie", "sweatshirt") and "summer" in text:
        risks.append("seasonal mismatch risk")
    return {
        "score": clamp_score(score),
        "strengths": strengths or ["proven POD staple"],
        "risks": risks,
        "source": "catalog text proxy",
    }


def persona_fit(product: Dict[str, Any], market_profile: Dict[str, Any], criteria: Dict[str, Any]) -> Dict[str, Any]:
    category = infer_category(product)
    query = (criteria.get("summary", "") or "").lower()
    persona = "General Gift Buyers"
    score = 68.0
    if "pet" in query or "cat" in query or "dog" in query:
        persona = "Gen Z Pet Lovers"
        if category in ("tshirt", "tanktop", "tote", "mug"):
            score += 22
    elif category in ("tanktop", "tshirt"):
        persona = "Gen Z and Millennials"
        score += 12
    elif category in ("hoodie", "sweatshirt"):
        persona = "Streetwear and Cozy Apparel Buyers"
        score += 10
    elif category in ("mug", "acrylic"):
        persona = "Gift Shoppers"
        score += 12
    return {
        "persona": persona,
        "score": clamp_score(score),
    }


def compatibility_score(product: Dict[str, Any], criteria: Dict[str, Any]) -> float:
    category = infer_category(product)
    query = (criteria.get("summary", "") or "").lower()
    score = 72.0
    if any(token in query for token in ["cat", "dog", "cute", "pet"]):
        if category in ("tshirt", "tanktop", "tote", "mug"):
            score += 22
        elif category == "blanket":
            score -= 20
    if any(token in query for token in ["fitness", "gym", "summer"]):
        if category in ("tanktop", "tshirt"):
            score += 18
        if category in ("hoodie", "sweatshirt"):
            score -= 12
    return clamp_score(score)


def pricing_profit(product: Dict[str, Any], market_profile: Dict[str, Any]) -> Dict[str, Any]:
    category = infer_category(product)
    cost = safe_float(product.get("base_cost"))
    if cost <= 0:
        cost = {
            "tshirt": 9.5,
            "tanktop": 9.0,
            "hoodie": 19.5,
            "sweatshirt": 16.0,
            "mug": 5.5,
            "tote": 8.0,
            "acrylic": 6.0,
            "poster": 7.0,
        }.get(category, 10.0)

    market_avg = safe_float(market_profile.get("avg_price"), 29.0)
    category_anchor = {
        "hoodie": max(market_avg + 16, cost * 2.1),
        "sweatshirt": max(market_avg + 10, cost * 2.0),
        "tanktop": max(market_avg - 4, cost * 2.1),
        "mug": max(19.0, cost * 2.4),
        "tote": max(24.0, cost * 2.2),
    }.get(category, max(market_avg, cost * 2.2))
    selling_price = round(category_anchor + 0.99, 2)
    profit = round(selling_price - cost, 2)
    margin = round((profit / selling_price) * 100, 1) if selling_price else 0.0
    margin_score = clamp_score(margin * 1.35)
    roi = round((profit / cost) * 100, 1) if cost else 0.0

    return {
        "cost": round(cost, 2),
        "selling_price": selling_price,
        "profit": profit,
        "margin": margin,
        "roi": roi,
        "margin_score": margin_score,
    }


def inventory_score(product: Dict[str, Any]) -> float:
    status = product.get("inventory_status", "unknown")
    if status == "available":
        return 92.0
    if status == "out_of_stock":
        return 0.0
    return 45.0


def expected_revenue(product: Dict[str, Any], final_score: float, profit_data: Dict[str, Any]) -> float:
    demand_units = max(1.0, final_score / 2.5)
    return round(demand_units * safe_float(profit_data.get("selling_price")), 2)


def calculate_final_score(breakdown: Dict[str, float]) -> float:
    total = 0.0
    for key, weight in SCORING_WEIGHTS.items():
        total += safe_float(breakdown.get(key), 0.0) * weight
    return round(clamp_score(total), 2)


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
