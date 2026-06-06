"""
LangGraph Nodes - Tất cả node functions của BurgerPrintsAgent
Dùng Gemini (langchain-google-genai) làm LLM
"""
import json
import os
import re
import logging
from typing import List

from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from agent.graph.state import AgentState
from agent.services import burgerprints as bp_api
from agent.services.catalog_store import (
    annotate_inventory,
    build_catalog_index,
    canonicalize_short_code,
    extract_out_of_stock_ids,
    validate_product_list,
)
from agent.services.commerce_intel import (
    calculate_final_score,
    compatibility_score,
    competition_score,
    expected_revenue,
    infer_category,
    infer_market,
    infer_season,
    infer_weather,
    inventory_score,
    market_fit_score,
    persona_fit,
    pricing_profit,
    review_score,
    season_fit_score,
    trend_score,
    weather_fit_score,
)
from agent.services.html_parser import normalize_product

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM init
# ---------------------------------------------------------------------------

FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]


def _get_llm(temperature: float = 0.1) -> ChatGoogleGenerativeAI:
    api_key = getattr(settings, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    model = getattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )


def _invoke_with_retry(llm, messages, max_retries: int = 3):
    """Gọi LLM với retry khi bị rate limit (429)"""
    import time
    last_error = None
    for attempt in range(max_retries):
        try:
            return llm.invoke(messages)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # Thử model nhẹ hơn
                api_key = getattr(settings, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
                for fallback_model in FALLBACK_MODELS[1:]:  # Skip default model
                    try:
                        fallback_llm = ChatGoogleGenerativeAI(
                            model=fallback_model,
                            google_api_key=api_key,
                            temperature=0.1,
                        )
                        logger.info(f"Switching to fallback model: {fallback_model}")
                        return fallback_llm.invoke(messages)
                    except Exception as fe:
                        if "429" not in str(fe) and "RESOURCE_EXHAUSTED" not in str(fe):
                            raise fe
                        continue
                wait = 2 ** attempt
                logger.warning(f"Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                last_error = e
            else:
                raise e
    raise last_error



# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------

class IntentOutput(BaseModel):
    intent: str = Field(
        description="One of: recommend_product, compare_product, check_stock, create_order, general_inquiry"
    )
    location_preference: str = Field(default="", description="Market/location: US, EU, China, Vietnam, etc.")
    max_lead_time: int = Field(default=999, description="Max acceptable lead time in business days")
    market: str = Field(default="", description="Target selling market")
    print_method: str = Field(default="", description="Preferred print method: DTG, Sublimation, etc.")
    product_names: List[str] = Field(default_factory=list, description="Specific product names or codes mentioned")
    budget_concern: bool = Field(default=False, description="User mentioned cost/price concern")
    summary: str = Field(default="", description="Brief summary of user intent in Vietnamese")


class ResponseOutput(BaseModel):
    response: str = Field(description="Câu trả lời đầy đủ cho người dùng bằng tiếng Việt")
    reasons: List[str] = Field(default_factory=list, description="Danh sách lý do chọn sản phẩm")


# ---------------------------------------------------------------------------
# Rule-based intent detection (fallback khi LLM không khả dụng)
# ---------------------------------------------------------------------------

def _rule_based_intent(query: str) -> dict:
    """
    Phân tích intent bằng keyword matching - không cần LLM.
    Luôn trả về kết quả hữu ích dựa trên từ khóa trong câu hỏi.
    """
    q = query.lower()

    # ── Intent detection ──
    intent = "recommend_product"  # default

    compare_kw = [
        "so sánh", "so sanh", "compare", "vs", " v ", "khác nhau", "khac nhau",
        "difference", "đối chiếu", "doi chieu", "giữa", "giua",
    ]
    stock_kw = [
        "hết hàng", "het hang", "còn hàng", "con hang", "tồn kho", "ton kho",
        "out of stock", "available", "stock", "còn không", "con khong",
    ]
    order_kw = [
        "tạo đơn", "tao don", "đặt hàng", "dat hang", "order", "mua", "purchase",
        "checkout", "đặt mua", "dat mua",
    ]

    if any(kw in q for kw in compare_kw):
        intent = "compare_product"
    elif any(kw in q for kw in stock_kw):
        intent = "check_stock"
    elif any(kw in q for kw in order_kw):
        intent = "create_order"

    # ── Location preference ──
    location_preference = ""
    loc_map = {
        "US": [
            "mỹ", "my", "us ", "usa", "united states", "america", "american",
            "thị trường mỹ", "thi truong my", "market us", "cho mỹ", "cho my",
        ],
        "EU": [
            "eu", "châu âu", "chau au", "europe", "european",
            "đức", "duc", "germany", "pháp", "phap", "france",
            " anh", "uk", "poland", "ba lan", "netherlands", "hà lan", "ha lan",
            "sang duc", "sang chau au", "thi truong eu",
        ],
        "China": ["trung quốc", "trung quoc", "china", "chinese"],
        "Vietnam": ["việt nam", "viet nam", "vietnam", "vn"],
    }
    for loc, keywords in loc_map.items():
        if any(kw in q for kw in keywords):
            location_preference = loc
            break

    # ── Max lead time ──
    max_lead_time = 999
    fast_kw = [
        "nhanh", "fast", "gấp", "gap", "urgent", "quick",
        "ngay", "sớm", "som", "nhanh nhất", "nhanh nhat",
    ]
    if any(kw in q for kw in fast_kw):
        max_lead_time = 5

    # ── Print method ──
    print_method = ""
    if "dtg" in q:
        print_method = "DTG"
    elif "dtf" in q:
        print_method = "DTF"
    elif "sublimation" in q or "sub" in q:
        print_method = "Sublimation"
    elif "aop" in q or "all over" in q:
        print_method = "AOP"
    elif "embroidery" in q or "thêu" in q or "theu" in q:
        print_method = "Embroidery"

    # ── Product names ──
    import re as _re
    found = _re.findall(
        r"(?:gildan|stanley|bella|canvas|next level|hanes|comfort colors|champion|\bG|\bUSG|\bEUG)\s*\d+",
        query, flags=_re.IGNORECASE
    )
    product_names = [f.strip() for f in found]

    # ── Budget concern ──
    budget_kw = [
        "rẻ", "re", "cheap", "giá thấp", "gia thap", "budget",
        "cost", "giá", "gia", "tiết kiệm", "tiet kiem", "affordable",
    ]
    budget_concern = any(kw in q for kw in budget_kw)

    return {
        "intent": intent,
        "location_preference": location_preference,
        "max_lead_time": max_lead_time,
        "market": location_preference,
        "print_method": print_method,
        "product_names": product_names,
        "budget_concern": budget_concern,
        "summary": query[:100],
    }


# ---------------------------------------------------------------------------
# Node 1: detect_intent
# ---------------------------------------------------------------------------

def detect_intent_node(state: AgentState) -> AgentState:
    """Phân tích intent: dùng Gemini LLM trước, fallback về rule-based nếu LLM lỗi"""
    query = state.get("query", "")
    history = state.get("conversation_history", [])

    # Thử LLM trước
    try:
        llm = _get_llm(temperature=0.1)

        history_text = ""
        if history:
            history_text = "\n".join([
                f"{m['role'].upper()}: {m['content']}"
                for m in history[-4:]
            ])

        system_prompt = """Bạn là AI assistant phân tích intent của seller POD (Print on Demand) trên nền tảng BurgerPrints.

Phân tích câu hỏi và trả về JSON với các trường sau:
- intent: "recommend_product" | "compare_product" | "check_stock" | "create_order" | "general_inquiry"
- location_preference: thị trường ưu tiên (US/EU/China/Vietnam/...)
- max_lead_time: thời gian fulfillment tối đa chấp nhận được (số ngày, mặc định 999)
- market: thị trường bán hàng mục tiêu
- print_method: phương pháp in ưa thích (DTG/Sublimation/...)
- product_names: danh sách tên/mã sản phẩm được đề cập
- budget_concern: true nếu người dùng quan tâm giá
- summary: tóm tắt ngắn gọn nhu cầu

Ví dụ:
- "Tôi muốn bán áo thun cho thị trường Mỹ" -> intent: recommend_product, location_preference: US, market: US
- "So sánh Gildan 5000 và Gildan 64000" -> intent: compare_product, product_names: ["Gildan 5000", "Gildan 64000"]
- "Sản phẩm này còn hàng không?" -> intent: check_stock
- "Tạo đơn hàng cho tôi" -> intent: create_order"""

        user_content = query
        if history_text:
            user_content = f"Lịch sử hội thoại:\n{history_text}\n\nCâu hỏi hiện tại: {query}"

        llm_structured = llm.with_structured_output(IntentOutput)
        result: IntentOutput = _invoke_with_retry(llm_structured, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])

        logger.info(f"LLM intent: {result.intent} | loc: {result.location_preference}")
        return {
            **state,
            "intent": result.intent,
            "extracted_criteria": {
                "location_preference": result.location_preference,
                "max_lead_time": result.max_lead_time,
                "market": result.market,
                "print_method": result.print_method,
                "product_names": result.product_names,
                "budget_concern": result.budget_concern,
                "summary": result.summary,
            },
        }

    except Exception as e:
        logger.warning(f"LLM intent failed, using rule-based: {e}")
        # Fallback: rule-based intent detection
        rb = _rule_based_intent(query)
        logger.info(f"Rule-based intent: {rb['intent']} | loc: {rb['location_preference']}")
        return {
            **state,
            "intent": rb["intent"],
            "extracted_criteria": rb,
            "error": "",  # Không hiện lỗi LLM với user
        }


# ---------------------------------------------------------------------------
# Node 2: fetch_catalog
# ---------------------------------------------------------------------------

def fetch_catalog_node(state: AgentState) -> AgentState:
    """Gọi GET /v2/product để lấy danh sách sản phẩm"""
    try:
        products_raw = bp_api.get_products(limit=500)
        # get_products() trả về list trực tiếp
        if not isinstance(products_raw, list):
            products_raw = []
        catalog_index = build_catalog_index(products_raw)
        return {
            **state,
            "products_raw": products_raw,
            "products_norm": catalog_index.get("products_norm", []),
            "catalog_index": catalog_index,
            "error": "",
        }
    except Exception as e:
        logger.error(f"fetch_catalog_node error: {e}")
        return {
            **state,
            "products_raw": [],
            "products_norm": [],
            "catalog_index": {},
            "error": f"Không lấy được catalog: {e}",
        }



# ---------------------------------------------------------------------------
# Node 3: fetch_product_detail (for compare)
# ---------------------------------------------------------------------------

def fetch_product_detail_node(state: AgentState) -> AgentState:
    """Gọi GET /v2/product/{short_code} cho từng sản phẩm cần so sánh"""
    criteria = state.get("extracted_criteria", {})
    product_names = criteria.get("product_names", [])
    catalog_index = state.get("catalog_index", {}) or {}

    # Nếu chưa có catalog, fetch trước
    products_raw = state.get("products_raw", [])
    if not products_raw:
        try:
            products_raw = bp_api.get_products(limit=500)
            catalog_index = build_catalog_index(products_raw)
        except Exception as e:
            return {**state, "error": str(e)}

    # Tìm sản phẩm theo tên/short_code
    compare_products = []
    for product in products_raw:
        name = (product.get("name", "") or product.get("shortCodeName", "") or "").lower()
        sku = canonicalize_short_code(product.get("short_code") or product.get("shortCode") or "")
        for pname in product_names:
            pname_lower = pname.lower().replace(" ", "").replace("-", "")
            sku_clean = sku.replace(" ", "").replace("-", "")
            if pname_lower in name.replace(" ", "") or pname_lower in sku_clean or sku_clean in pname_lower:
                try:
                    detail = bp_api.get_product_detail(sku)
                    detail_payload = detail if isinstance(detail, dict) and detail else product
                    normalized_detail = normalize_product(detail_payload)
                    compare_products.append(normalized_detail)
                except Exception:
                    compare_products.append(normalize_product(product))
                break

    # Nếu không tìm được qua name, dùng 3 sản phẩm đầu
    if not compare_products and products_raw:
        compare_products = [normalize_product(p) for p in products_raw[:3]]

    return {
        **state,
        "products_raw": products_raw,
        "compare_products": compare_products,
        "catalog_index": catalog_index or build_catalog_index(products_raw),
    }



# ---------------------------------------------------------------------------
# Node 4: check_stock
# ---------------------------------------------------------------------------

def check_stock_node(state: AgentState) -> AgentState:
    """Gọi GET /v2/product/out-of-stock"""
    try:
        data = bp_api.get_out_of_stock()
        oos_ids = extract_out_of_stock_ids(data)
        inventory_snapshot = {
            "out_of_stock_ids": oos_ids,
            "source": "burgerprints:v2/product/out-of-stock",
            "count": len(oos_ids),
        }
        return {
            **state,
            "out_of_stock_ids": oos_ids,
            "inventory_snapshot": inventory_snapshot,
            "error": "",
        }
    except Exception as e:
        logger.error(f"check_stock_node error: {e}")
        return {
            **state,
            "out_of_stock_ids": [],
            "inventory_snapshot": {"out_of_stock_ids": [], "source": "error", "count": 0},
            "error": f"Không kiểm tra được tồn kho: {e}",
        }


# ---------------------------------------------------------------------------
# Node 5: process_catalog
# ---------------------------------------------------------------------------

def process_catalog_node(state: AgentState) -> AgentState:
    """Parse html_desc từ tất cả sản phẩm trong catalog"""
    products_raw = state.get("products_raw", [])
    products_norm = [normalize_product(p) for p in products_raw]
    catalog_index = build_catalog_index(products_raw)
    return {
        **state,
        "products_norm": products_norm,
        "catalog_index": catalog_index,
    }


# ---------------------------------------------------------------------------
# Commerce Decision Agent nodes
# ---------------------------------------------------------------------------

def market_analysis_node(state: AgentState) -> AgentState:
    """Analyze target market and preferred product categories."""
    criteria = state.get("extracted_criteria", {})
    query = state.get("query", "")
    market_context = infer_market(criteria, query)
    return {**state, "market_context": market_context}


def inventory_analysis_node(state: AgentState) -> AgentState:
    """Verify inventory status from BurgerPrints out-of-stock ground truth."""
    products = state.get("products_norm", [])
    oos_ids = state.get("out_of_stock_ids", [])

    if not oos_ids:
        try:
            data = bp_api.get_out_of_stock()
            oos_ids = extract_out_of_stock_ids(data)
        except Exception as e:
            logger.warning(f"inventory_analysis_node stock check failed: {e}")
            oos_ids = []

    products_norm = annotate_inventory(products, oos_ids)
    candidates = [p for p in products_norm if p.get("inventory_status") != "out_of_stock"]
    inventory_snapshot = {
        "out_of_stock_ids": oos_ids,
        "source": "burgerprints:v2/product/out-of-stock",
        "count": len(oos_ids),
    }
    return {
        **state,
        "products_norm": products_norm,
        "candidates": candidates,
        "out_of_stock_ids": oos_ids,
        "inventory_snapshot": inventory_snapshot,
    }


def season_weather_node(state: AgentState) -> AgentState:
    """Infer current season and weather/climate context."""
    market_context = state.get("market_context", {}) or infer_market(state.get("extracted_criteria", {}), state.get("query", ""))
    season_context = infer_season(market_context)
    weather_context = infer_weather(state.get("extracted_criteria", {}), market_context)
    return {
        **state,
        "market_context": market_context,
        "season_context": season_context,
        "weather_context": weather_context,
    }


def demand_analysis_node(state: AgentState) -> AgentState:
    """Calculate trend, competition, and review proxy signals per product."""
    products = state.get("candidates") or state.get("products_norm", [])
    market_context = state.get("market_context", {})

    demand_signals = {}
    for product in products:
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if not code:
            continue
        review = review_score(product)
        demand_signals[code] = {
            "trend_score": trend_score(product, market_context),
            "competition_score": competition_score(product, market_context),
            "review_score": review.get("score", 0),
            "review_strengths": review.get("strengths", []),
            "review_risks": review.get("risks", []),
        }

    return {**state, "demand_signals": demand_signals}


def pricing_profit_node(state: AgentState) -> AgentState:
    """Calculate selling price, margin, ROI, and profit per candidate."""
    products = state.get("candidates") or state.get("products_norm", [])
    market_context = state.get("market_context", {})

    pricing_context = {}
    for product in products:
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if not code:
            continue
        pricing_context[code] = pricing_profit(product, market_context)

    return {**state, "pricing_context": pricing_context}


def persona_compatibility_node(state: AgentState) -> AgentState:
    """Score likely buyer persona and design/product compatibility."""
    products = state.get("candidates") or state.get("products_norm", [])
    market_context = state.get("market_context", {})
    criteria = state.get("extracted_criteria", {})

    persona_context = {}
    compatibility_context = {}
    for product in products:
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if not code:
            continue
        persona_context[code] = persona_fit(product, market_context, criteria)
        compatibility_context[code] = {
            "score": compatibility_score(product, criteria),
            "category": infer_category(product),
        }

    return {
        **state,
        "persona_context": persona_context,
        "compatibility_context": compatibility_context,
    }


# ---------------------------------------------------------------------------
# Node 6: deterministic recommendation engine
# ---------------------------------------------------------------------------

def decision_engine_node(state: AgentState) -> AgentState:
    """
    Rank products with deterministic commerce scoring.
    LLM is not allowed to decide the winner.
    """
    products_norm = state.get("candidates") or state.get("products_norm", [])
    criteria = state.get("extracted_criteria", {})
    oos_ids = state.get("out_of_stock_ids", [])
    catalog_index = state.get("catalog_index", {}) or {}
    market_context = state.get("market_context", {}) or infer_market(criteria, state.get("query", ""))
    season_context = state.get("season_context", {}) or infer_season(market_context)
    weather_context = state.get("weather_context", {}) or infer_weather(criteria, market_context)
    demand_signals = state.get("demand_signals", {})
    pricing_context = state.get("pricing_context", {})
    persona_context = state.get("persona_context", {})
    compatibility_context = state.get("compatibility_context", {})
    oos_set = {canonicalize_short_code(x) for x in oos_ids}

    candidates = []
    for p in products_norm:
        code = canonicalize_short_code(p.get("short_code") or p.get("id"))
        if not code:
            continue
        if code in oos_set:
            continue
        product = {**p, "inventory_status": p.get("inventory_status", "available"), "sku_valid": True}
        candidates.append(product)

    scored = []
    evidence = []
    for p in candidates:
        code = canonicalize_short_code(p.get("short_code") or p.get("id"))
        demand = demand_signals.get(code, {})
        pricing = pricing_context.get(code) or pricing_profit(p, market_context)
        persona = persona_context.get(code) or persona_fit(p, market_context, criteria)
        compat = compatibility_context.get(code) or {
            "score": compatibility_score(p, criteria),
            "category": infer_category(p),
        }

        breakdown = {
            "trend": demand.get("trend_score", trend_score(p, market_context)),
            "market_fit": market_fit_score(p, market_context),
            "season_fit": season_fit_score(p, season_context),
            "weather_fit": weather_fit_score(p, weather_context),
            "inventory": inventory_score(p),
            "margin": pricing.get("margin_score", 0),
            "review": demand.get("review_score", review_score(p).get("score", 0)),
            "competition": demand.get("competition_score", competition_score(p, market_context)),
            "persona": persona.get("score", 0),
            "compatibility": compat.get("score", 0),
        }
        score = calculate_final_score(breakdown)

        p["category"] = compat.get("category", infer_category(p))
        p["inventory_status"] = "out_of_stock" if code in oos_set else p.get("inventory_status", "available")
        p["sku_valid"] = True
        p["source_verified"] = "catalog"
        p["base_cost"] = pricing.get("cost", p.get("base_cost", 0))
        p["suggested_selling_price"] = pricing.get("selling_price", 0)
        p["margin"] = pricing.get("margin", 0)
        p["profit"] = pricing.get("profit", 0)
        p["roi"] = pricing.get("roi", 0)
        p["expected_revenue"] = expected_revenue(p, score, pricing)
        p["recommended_audience"] = persona.get("persona", "General Gift Buyers")
        p["risks"] = _build_product_risks(p, breakdown, demand, season_context, weather_context)

        scored.append({
            "product": p,
            "score": score,
            "breakdown": breakdown,
            "evidence": {
                "market": market_context,
                "season": season_context,
                "weather": weather_context,
                "pricing": pricing,
                "demand": demand,
                "persona": persona,
                "compatibility": compat,
            },
        })
        evidence.append({
            "short_code": code,
            "name": p.get("name", ""),
            "score": score,
            "breakdown": breakdown,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    winner = scored[0]["product"] if scored else None
    reasons = _build_reasons(winner, scored[0].get("breakdown", {}) if scored else {}, criteria)

    return {
        **state,
        "candidates": candidates,
        "scores": scored[:10],  # top 10
        "winner": winner,
        "reasons": reasons,
        "evidence": evidence[:10],
        "catalog_index": catalog_index or build_catalog_index(products_norm),
    }


def _build_reasons(product: dict, breakdown: dict, criteria: dict) -> List[str]:
    if not product:
        return ["Không tìm thấy sản phẩm phù hợp"]

    reasons = []
    loc = product.get("location", "Unknown")
    proc = product.get("processing_time", "Unknown")
    material = product.get("material", "Unknown")
    pm = product.get("print_method", "Unknown")

    if loc != "Unknown":
        reasons.append(f"📍 Sản xuất tại **{loc}** - phù hợp với thị trường mục tiêu")
    if proc != "Unknown":
        reasons.append(f"⏱️ Thời gian xử lý **{proc}** - giao hàng nhanh")
    if material != "Unknown":
        reasons.append(f"🧵 Chất liệu **{material}** - chất lượng tốt")
    if pm != "Unknown":
        reasons.append(f"🖨️ Công nghệ in **{pm}** - phổ biến và ổn định")
    if breakdown:
        reasons.append(f"📈 Market fit **{breakdown.get('market_fit', 0):.0f}/100**, season fit **{breakdown.get('season_fit', 0):.0f}/100**")
        reasons.append(f"💰 Margin score **{breakdown.get('margin', 0):.0f}/100**, trend score **{breakdown.get('trend', 0):.0f}/100**")
    if product.get("recommended_audience"):
        reasons.append(f"🎯 Nhóm khách hàng phù hợp: **{product.get('recommended_audience')}**")

    return reasons


def _build_product_risks(
    product: dict,
    breakdown: dict,
    demand: dict,
    season_context: dict,
    weather_context: dict,
) -> List[str]:
    risks = list(demand.get("review_risks", []) or [])
    category = product.get("category") or infer_category(product)
    season = season_context.get("season", "")
    avg_temp = weather_context.get("avg_temp")

    if product.get("inventory_status") == "unknown":
        risks.append("inventory freshness is unknown")
    if breakdown.get("competition", 100) < 60:
        risks.append("high market saturation")
    if breakdown.get("season_fit", 100) < 55:
        risks.append(f"{category} is weak for {season}")
    if avg_temp is not None and category in ("hoodie", "sweatshirt") and float(avg_temp) >= 28:
        risks.append("warm weather can reduce apparel demand")
    if not risks:
        risks.append("no major risk from available signals")
    return risks[:4]


def _suggest_selling_price(base_cost: float, product: dict) -> float:
    """Simple deterministic pricing heuristic based on base cost."""
    if not base_cost or base_cost <= 0:
        return 0.0

    markup = 2.2
    name = (product.get("name", "") or "").lower()
    if "hoodie" in name or "sweatshirt" in name:
        markup = 2.35
    elif "tank" in name:
        markup = 2.15
    elif "mug" in name or "acrylic" in name:
        markup = 2.5

    price = round(base_cost * markup + 0.01, 2)
    return price


# ---------------------------------------------------------------------------
# Node 7: compare_node
# ---------------------------------------------------------------------------

def compare_node(state: AgentState) -> AgentState:
    """Tạo bảng so sánh cho các sản phẩm"""
    compare_products = state.get("compare_products", [])
    out_of_stock_ids = state.get("out_of_stock_ids", [])
    base_products = [
        p if p.get("location") or p.get("processing_time") else normalize_product(p)
        for p in compare_products
        if isinstance(p, dict)
    ]
    products_norm = annotate_inventory(base_products, out_of_stock_ids)

    return {
        **state,
        "products_norm": products_norm,
        "candidates": products_norm,
    }


# ---------------------------------------------------------------------------
# Node 8: suggest_alternatives (for out of stock)
# ---------------------------------------------------------------------------

def suggest_alternatives_node(state: AgentState) -> AgentState:
    """Đề xuất sản phẩm thay thế khi hết hàng"""
    products_norm = state.get("products_norm", [])
    oos_ids = state.get("out_of_stock_ids", [])

    # Lọc sản phẩm còn hàng
    oos_set = {canonicalize_short_code(x) for x in oos_ids}
    alternatives = [
        {**p, "inventory_status": "available"}
        for p in products_norm
        if canonicalize_short_code(p.get("short_code") or p.get("id")) not in oos_set
    ][:5]

    return {**state, "alternatives": alternatives}


# ---------------------------------------------------------------------------
# Node 9b: validate_output
# ---------------------------------------------------------------------------

def validate_output_node(state: AgentState) -> AgentState:
    """Sanitize products and ensure every returned SKU exists in the canonical catalog."""
    catalog_index = state.get("catalog_index", {}) or build_catalog_index(state.get("products_raw", []))

    scores = state.get("scores", [])
    validated_scores = []
    validation_errors = []
    by_short_code = catalog_index.get("by_short_code", {}) or {}

    for item in scores:
        product = item.get("product", {}) if isinstance(item, dict) else {}
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if not code or code not in by_short_code:
            validation_errors.append(
                f"Dropped unknown SKU from scores: {product.get('short_code') or product.get('id') or '?'}"
            )
            continue
        canonical_product = {**by_short_code[code], **product}
        validated_scores.append({**item, "product": canonical_product})

    winner = state.get("winner")
    if isinstance(winner, dict):
        winner_code = canonicalize_short_code(winner.get("short_code") or winner.get("id"))
        if winner_code and winner_code in by_short_code:
            winner = {**by_short_code[winner_code], **winner}
        else:
            validation_errors.append(
                f"Invalid winner SKU removed: {winner.get('short_code') or winner.get('id') or '?'}"
            )
            winner = None

    compare_products = state.get("compare_products", [])
    validated_compare = []
    for product in compare_products:
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if code and code in by_short_code:
            validated_compare.append({**by_short_code[code], **product})
        else:
            validation_errors.append(f"Unknown product identifier: {product.get('short_code') or product.get('id') or '?'}")

    alternatives = state.get("alternatives", [])
    validated_alternatives = []
    for product in alternatives:
        code = canonicalize_short_code(product.get("short_code") or product.get("id"))
        if code and code in by_short_code:
            validated_alternatives.append({**by_short_code[code], **product})
        else:
            validation_errors.append(f"Unknown product identifier: {product.get('short_code') or product.get('id') or '?'}")

    if not validated_scores and scores:
        validation_errors.append("All scored products were removed during validation")

    return {
        **state,
        "catalog_index": catalog_index,
        "scores": validated_scores,
        "winner": winner,
        "compare_products": validated_compare,
        "alternatives": validated_alternatives,
        "validation_errors": validation_errors,
    }


# ---------------------------------------------------------------------------
# Node 9: order_builder
# ---------------------------------------------------------------------------

def order_builder_node(state: AgentState) -> AgentState:
    """Xây dựng order payload từ query người dùng"""
    query = state.get("query", "")
    catalog_index = state.get("catalog_index", {}) or {}
    products_raw = state.get("products_raw", [])
    if not catalog_index.get("by_short_code"):
        try:
            products_raw = bp_api.get_products(limit=500)
            catalog_index = build_catalog_index(products_raw)
        except Exception as e:
            logger.warning(f"order_builder_node catalog validation failed: {e}")
    by_short_code = catalog_index.get("by_short_code", {}) or {}
    known_codes = set(by_short_code.keys())

    # Try to validate an SKU mentioned in the query, but never invent one.
    query_tokens = re.findall(r"[A-Z0-9][A-Z0-9\-]{2,}", query.upper())
    validated_sku = ""
    for token in query_tokens:
        code = canonicalize_short_code(token)
        if code in known_codes:
            validated_sku = code
            break

    if validated_sku:
        product_name = by_short_code[validated_sku].get("name", validated_sku)
        message = (
            f"Mình đã nhận diện SKU hợp lệ **{validated_sku}** ({product_name}). "
            "Để tạo đơn hàng an toàn, mình cần thêm: tên khách hàng, địa chỉ giao hàng và số lượng."
        )
    else:
        message = (
            "Để tạo đơn hàng, mình cần SKU hợp lệ, tên khách hàng, địa chỉ giao hàng và số lượng. "
            "Nếu bạn đã có SKU, hãy gửi đúng mã sản phẩm để mình kiểm tra lại trong catalog trước khi tạo đơn."
        )

    return {
        **state,
        "products_raw": products_raw,
        "catalog_index": catalog_index,
        "response_msg": message,
        "order_payload": {},
    }


# ---------------------------------------------------------------------------
# Node 10: generate_response
# ---------------------------------------------------------------------------

def generate_response_node(state: AgentState) -> AgentState:
    """Create a deterministic response from validated, canonical product data."""
    intent = state.get("intent", "")
    query = state.get("query", "")
    scores = state.get("scores", [])
    reasons = state.get("reasons", [])
    compare_products = state.get("compare_products", [])
    alternatives = state.get("alternatives", [])
    out_of_stock_ids = state.get("out_of_stock_ids", [])
    error = state.get("error", "")
    criteria = state.get("extracted_criteria", {})
    validation_errors = state.get("validation_errors", [])

    # Nếu đã có response_msg (từ order_builder), bỏ qua
    if state.get("response_msg") and intent == "create_order":
        return state

    if error and not scores and intent != "create_order":
        return {
            **state,
            "response_msg": f"❌ Xin lỗi, đã xảy ra lỗi: {error}. Vui lòng thử lại sau.",
            "reasons": [],
        }

    response = _build_deterministic_response(
        query=query,
        intent=intent,
        scores=scores,
        reasons=reasons,
        criteria=criteria,
        compare_products=compare_products,
        alternatives=alternatives,
        out_of_stock_ids=out_of_stock_ids,
        validation_errors=validation_errors,
    )
    return {**state, "response_msg": response}


def _build_deterministic_response(
    query: str,
    intent: str,
    scores: list,
    reasons: list,
    criteria: dict,
    compare_products: list,
    alternatives: list,
    out_of_stock_ids: list,
    validation_errors: list,
) -> str:
    """Compose a safe markdown response from canonical product data only."""
    loc = criteria.get("location_preference", "")
    max_lead = criteria.get("max_lead_time", 999)
    print_pref = criteria.get("print_method", "")

    header_notes = []
    if validation_errors:
        header_notes.append("> Validation gate removed non-canonical fields before response generation.")

    # ── Compare intent ──
    if intent == "compare_product" and (scores or compare_products):
        score_by_code = {
            canonicalize_short_code(item.get("product", {}).get("short_code")): item
            for item in scores
        }
        norm_cp = compare_products[:3] if compare_products else [item.get("product", {}) for item in scores[:3]]
        lines = [f"## ⚖️ So sánh sản phẩm theo yêu cầu: *\"{query}\"*"]
        if header_notes:
            lines.extend(header_notes)
        lines.append("")
        lines.append("| Tiêu chí | " + " | ".join(p.get('name','?')[:20] for p in norm_cp) + " |")
        lines.append("|---|" + "---|" * len(norm_cp))
        fields = [
            ("SKU", "short_code"),
            ("📍 Location", "location"),
            ("⏱️ Processing", "processing_time"),
            ("🧵 Material", "material"),
            ("🖨️ Print", "print_method"),
            ("📦 Inventory", "inventory_status"),
            ("🎯 Audience", "recommended_audience"),
        ]
        for label, key in fields:
            row = f"| {label} | " + " | ".join(str(p.get(key, "?")) for p in norm_cp) + " |"
            lines.append(row)
        score_fields = [
            ("Final Score", "score"),
            ("Trend Score", "trend"),
            ("Market Fit", "market_fit"),
            ("Season Fit", "season_fit"),
            ("Margin Score", "margin"),
            ("Competition Score", "competition"),
        ]
        for label, key in score_fields:
            values = []
            for p in norm_cp:
                item = score_by_code.get(canonicalize_short_code(p.get("short_code")))
                if not item:
                    values.append("?")
                elif key == "score":
                    values.append(f"{item.get('score', 0):.0f}")
                else:
                    values.append(f"{item.get('breakdown', {}).get(key, 0):.0f}")
            lines.append(f"| {label} | " + " | ".join(values) + " |")
        lines.append("")
        if scores:
            winner = scores[0].get("product", {})
            lines.append(f"**Kết luận:** `{winner.get('short_code', '?')}` thắng vì có tổng điểm cao nhất dựa trên market, season, inventory, margin và demand signals.")
        return "\n".join(lines)

    # ── Check stock intent ──
    if intent == "check_stock":
        alt_list = "\n".join(
            f"- **{p.get('name','?')}** (`{p.get('short_code','?')}`): {p.get('location','?')} | {p.get('processing_time','?')} | {p.get('inventory_status','unknown')}"
            for p in alternatives[:3]
        )
        oos_list = ", ".join(out_of_stock_ids[:10]) if out_of_stock_ids else "không xác định"
        return (
            f"## 📦 Kiểm tra tồn kho\n\n"
            f"Đã kiểm tra catalog BurgerPrints.\n\n"
            f"- Out of stock IDs: {oos_list}\n\n"
            + (f"**Sản phẩm thay thế được đề xuất:**\n{alt_list}" if alt_list else "Không tìm thấy sản phẩm thay thế phù hợp.")
            + "\n\n💡 Bạn muốn xem chi tiết sản phẩm nào?"
        )

    # ── Recommend product intent (default) ──
    if not scores:
        return "❌ Không tìm thấy sản phẩm phù hợp với yêu cầu. Vui lòng thử với tiêu chí khác."

    # Header theo query
    loc_label = f"thị trường **{loc}**" if loc else "nhu cầu của bạn"
    fast_label = f", giao hàng trong **≤{max_lead} ngày**" if max_lead < 999 else ""
    header = f"## 🏆 Sản phẩm có xác suất bán tốt nhất cho {loc_label}{fast_label}\n\n*Dựa trên câu hỏi: \"{query}\"*"
    if header_notes:
        header += "\n" + "\n".join(header_notes)
    header += "\n"

    # Top 3 sản phẩm
    product_lines = []
    for rank, item in enumerate(scores[:3], 1):
        p = item["product"]
        score = item["score"]
        breakdown = item.get("breakdown", {})
        medals = ["🥇", "🥈", "🥉"]
        medal = medals[rank - 1]
        product_lines.append(f"{medal} **{p.get('name', 'N/A')}** (`{p.get('short_code', 'N/A')}`) — Score: {score:.0f}/100")
        product_lines.append(f"   - 📈 Trend: **{breakdown.get('trend', 0):.0f}/100** | Market fit: **{breakdown.get('market_fit', 0):.0f}/100** | Season fit: **{breakdown.get('season_fit', 0):.0f}/100**")
        product_lines.append(f"   - 💰 Margin: **{p.get('margin', 0):.1f}%** | Profit/order: **${p.get('profit', 0):.2f}** | ROI: **{p.get('roi', 0):.0f}%**")
        product_lines.append(f"   - 📦 Inventory: **{p.get('inventory_status', 'unknown')}**")
        product_lines.append(f"   - 📍 Location: **{p.get('location', '?')}**")
        product_lines.append(f"   - ⏱️ Processing: **{p.get('processing_time', '?')}**")
        product_lines.append(f"   - 🧵 Material: {p.get('material', '?')}")
        product_lines.append(f"   - 🖨️ Print: {p.get('print_method', '?')}")
        product_lines.append(f"   - 🎯 Audience: **{p.get('recommended_audience', 'General Gift Buyers')}**")
        if p.get("suggested_selling_price"):
            product_lines.append(f"   - 💰 Suggested selling price: **${p.get('suggested_selling_price'):.2f}**")
        risks = p.get("risks") or []
        if risks:
            product_lines.append(f"   - ⚠️ Risks: {', '.join(risks[:3])}")

    # Lý do chọn #1
    reason_section = ""
    if reasons:
        reason_section = "\n\n**✅ Lý do đề xuất sản phẩm #1:**\n" + "\n".join(f"- {r}" for r in reasons)

    # CTA
    cta = "\n\n💬 Bạn muốn xem thêm chi tiết, so sánh sản phẩm, hoặc tạo đơn hàng không?"

    return header + "\n".join(product_lines) + reason_section + cta
