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
        description=(
            "One of: recommend_product | compare_product | check_stock | create_order "
            "| catalog_info | general_inquiry. "
            "catalog_info: user hỏi về catalog meta (partner nào có, loại sản phẩm, màu, location, price range, ...)"
        )
    )
    catalog_query_type: str = Field(
        default="",
        description="Khi intent=catalog_info, chỉ định loại câu hỏi: partners|product_types|colors|locations|print_methods|price_range|general"
    )
    location_preference: str = Field(default="", description="Market/location: US, EU, China, Vietnam, etc.")
    max_lead_time: int = Field(default=999, description="Max acceptable lead time in business days")
    market: str = Field(default="", description="Target selling market")
    print_method: str = Field(default="", description="Preferred print method: DTG, Sublimation, etc.")
    product_names: List[str] = Field(default_factory=list, description="Specific product names or codes mentioned")
    budget_concern: bool = Field(default=False, description="User mentioned cost/price concern")
    summary: str = Field(default="", description="Brief summary of user intent in Vietnamese")
    partner_preference: List[str] = Field(default_factory=list, description="Preferred partners: Spire, Bella + Canvas, Gildan, etc.")
    color_preference: List[str] = Field(default_factory=list, description="Preferred colors: black, white, blue, etc.")
    max_price: float = Field(default=9999.0, description="Maximum price limit")
    min_price: float = Field(default=0.0, description="Minimum price limit")
    skus: List[str] = Field(default_factory=list, description="Extracted SKU codes")
    list_all: bool = Field(
        default=False,
        description=(
            "True khi user muốn xem TOÀN BỘ danh sách sản phẩm thỏa điều kiện, không chỉ top 3. "
            "Dấu hiệu: 'toàn bộ', 'tất cả', 'danh sách đầy đủ', 'liệt kê', 'cho tôi hết', 'list all', 'all products'."
        )
    )


class ResponseOutput(BaseModel):
    response: str = Field(description="Câu trả lời đầy đủ cho người dùng bằng tiếng Việt")
    reasons: List[str] = Field(default_factory=list, description="Danh sách lý do chọn sản phẩm")


# ---------------------------------------------------------------------------
# Rule-based intent detection (fallback khi LLM không khả dụng)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Node 1: detect_intent
# ---------------------------------------------------------------------------

def detect_intent_node(state: AgentState) -> AgentState:
    """Phân tích intent: chỉ dùng Gemini LLM, không dùng rule-based."""
    query = state.get("query", "")
    history = state.get("conversation_history", [])

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
- intent: "recommend_product" | "compare_product" | "check_stock" | "create_order" | "catalog_info" | "general_inquiry"
- catalog_query_type: chỉ dùng khi intent=catalog_info → partners|product_types|colors|locations|print_methods|price_range|general
- location_preference: thị trường ưu tiên (US/EU/China/Vietnam/...)
- max_lead_time: thời gian fulfillment tối đa chấp nhận được (số ngày, mặc định 999)
- market: thị trường bán hàng mục tiêu
- print_method: phương pháp in ưa thích (DTG/Sublimation/...)
- product_names: danh sách tên/mã sản phẩm được đề cập
- budget_concern: true nếu người dùng quan tâm giá
- summary: tóm tắt ngắn gọn nhu cầu
- partner_preference: danh sách partner ưu tiên (Spire, Bella + Canvas, Gildan, ...)
- color_preference: danh sách màu ưu tiên
- max_price: giá tối đa (nếu đề cập)
- min_price: giá tối thiểu (nếu đề cập)
- skus: danh sách mã SKU cụ thể
- list_all: true khi user muốn xem TOÀN BỘ danh sách ("toàn bộ", "tất cả", "danh sách đầy đủ", "liệt kê", "cho tôi hết", "all", "list all")

CÁC INTENT VÀ VÍ DỤ:
1. recommend_product:
   - "Tôi muốn bán áo thun cho thị trường Mỹ" → recommend_product, location_preference: US
   - "Tìm áo màu đen, partner Spire, dưới $12, ship US" → recommend_product, partner_preference: [Spire], color_preference: [black], max_price: 12.0, location_preference: US
   - "Cho tôi toàn bộ tên sản phẩm còn hàng tại China" → recommend_product, location_preference: China, list_all: true
   - "Liệt kê tất cả sản phẩm kho US" → recommend_product, location_preference: US, list_all: true
   - "Seller mới nên bán gì?" → recommend_product

2. compare_product:
   - "So sánh Gildan 5000 và Gildan 64000" → compare_product, product_names: [Gildan 5000, Gildan 64000]

3. check_stock:
   - "Sản phẩm này còn hàng không?" → check_stock
   - "Bella + Canvas 3001 còn stock không?" → check_stock, product_names: [Bella + Canvas 3001]

4. create_order:
   - "Tạo đơn hàng cho tôi" → create_order

5. catalog_info (ĐẶC BIỆT - hỏi thông tin CATALOG META, không phải tìm sản phẩm):
   - "Hiện tại đang có những partner nào?" → catalog_info, catalog_query_type: partners
   - "Có những loại sản phẩm gì?" → catalog_info, catalog_query_type: product_types
   - "Có màu sắc nào trong catalog?" → catalog_info, catalog_query_type: colors
   - "Kho hàng ở đâu?" → catalog_info, catalog_query_type: locations
   - "Phương pháp in nào được hỗ trợ?" → catalog_info, catalog_query_type: print_methods
   - "Giá sản phẩm range bao nhiêu?" → catalog_info, catalog_query_type: price_range

6. general_inquiry:
   - "POD là gì?" → general_inquiry
   - "Làm sao bắt đầu bán POD?" → general_inquiry"""

        user_content = query
        if history_text:
            user_content = f"Lịch sử hội thoại:\n{history_text}\n\nCâu hỏi hiện tại: {query}"

        llm_structured = llm.with_structured_output(IntentOutput)
        result: IntentOutput = _invoke_with_retry(llm_structured, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])

        logger.info(f"LLM intent: {result.intent} | cat_type: {result.catalog_query_type} | loc: {result.location_preference} | list_all: {getattr(result, 'list_all', False)}")
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
                "catalog_query_type": result.catalog_query_type,
                "partner_preference": getattr(result, 'partner_preference', []) or [],
                "color_preference": getattr(result, 'color_preference', []) or [],
                "max_price": getattr(result, 'max_price', 9999.0) or 9999.0,
                "min_price": getattr(result, 'min_price', 0.0) or 0.0,
                "skus": getattr(result, 'skus', []) or [],
                "list_all": getattr(result, 'list_all', False),
            },
        }

    except Exception as e:
        logger.error(f"LLM intent failed: {e}")
        # Nếu LLM lỗi, mặc định về general_inquiry thay vì rule-based
        return {
            **state,
            "intent": "general_inquiry",
            "extracted_criteria": {},
            "error": str(e),
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
    oos_ids = state.get("out_of_stock_ids", None)
    snapshot = state.get("inventory_snapshot", {}) or {}
    if snapshot.get("source") == "error":
        oos_ids = None

    if oos_ids is None:
        products_norm = annotate_inventory(products, None)
        inventory_snapshot = {
            "out_of_stock_ids": [],
            "source": "unknown",
            "count": 0,
        }
        return {
            **state,
            "products_norm": products_norm,
            "candidates": products_norm,
            "out_of_stock_ids": [],
            "inventory_snapshot": inventory_snapshot,
        }

    if not oos_ids:
        try:
            data = bp_api.get_out_of_stock()
            oos_ids = extract_out_of_stock_ids(data)
        except Exception as e:
            logger.warning(f"inventory_analysis_node stock check failed: {e}")
            products_norm = annotate_inventory(products, None)
            inventory_snapshot = {
                "out_of_stock_ids": [],
                "source": "error",
                "count": 0,
            }
            return {
                **state,
                "products_norm": products_norm,
                "candidates": products_norm,
                "out_of_stock_ids": [],
                "inventory_snapshot": inventory_snapshot,
            }

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
    oos_ids = state.get("out_of_stock_ids") or []
    catalog_index = state.get("catalog_index", {}) or {}
    market_context = state.get("market_context", {}) or infer_market(criteria, state.get("query", ""))
    season_context = state.get("season_context", {}) or infer_season(market_context)
    weather_context = state.get("weather_context", {}) or infer_weather(criteria, market_context)
    demand_signals = state.get("demand_signals", {})
    pricing_context = state.get("pricing_context", {})
    persona_context = state.get("persona_context", {})
    compatibility_context = state.get("compatibility_context", {})
    oos_set = {canonicalize_short_code(x) for x in oos_ids or []}

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

    # Nếu user muốn toàn bộ danh sách → trả về tất cả; ngược lại giới hạn top 50
    list_all = criteria.get("list_all", False)
    score_limit = len(scored) if list_all else 50

    return {
        **state,
        "candidates": candidates,
        "scores": scored[:score_limit],
        "winner": winner,
        "reasons": reasons,
        "evidence": evidence[:score_limit],
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

    # Nếu đã có response_msg từ catalog_info, zorinask, hoặc create_order → bỏ qua
    if state.get("response_msg") and intent in ("create_order", "catalog_info", "general_inquiry"):
        return state

    if error and not scores and intent != "create_order":
        return {
            **state,
            "response_msg": f"❌ Xin lỗi, đã xảy ra lỗi: {error}. Vui lòng thử lại sau.",
            "reasons": [],
        }

    try:
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
    except Exception:
        response = ""

    if not response:
        top = scores[0].get("product", {}) if scores else {}
        label = top.get("name") or top.get("short_code") or "sản phẩm này"
        response = f"Mình chưa kết xuất được phần giải thích so sánh. Bạn thử hỏi: `Phân tích chi tiết {label}` hoặc `So sánh [SP1] với [SP2]`."

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
    criteria = criteria if isinstance(criteria, dict) else {}
    def _extract_requested_count(text: str) -> int:
        q = (text or "").lower()
        m = re.search(r"\b(\d{1,3})\b\s*(?:sản\s*phẩm|sp)\b", q)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0
        m = re.search(r"\b(?:top|best)\s*(\d{1,3})\b", q)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0
        return 0

    def _format_filters(criteria_dict: dict) -> str:
        if not isinstance(criteria_dict, dict):
            criteria_dict = {}
        parts = []
        loc_val = (criteria_dict.get("location_preference") or "").strip()
        if loc_val:
            parts.append(f"📍 {loc_val.upper()}")
        pm_val = (criteria_dict.get("print_method") or "").strip()
        if pm_val:
            parts.append(f"🖨️ {pm_val}")
        max_lead_val = criteria_dict.get("max_lead_time", 999)
        if isinstance(max_lead_val, int) and 0 < max_lead_val < 999:
            parts.append(f"⏱️ ≤{max_lead_val} ngày")
        max_price_val = criteria_dict.get("max_price", 9999.0)
        try:
            max_price_val = float(max_price_val)
        except Exception:
            max_price_val = 9999.0
        if 0 < max_price_val < 9999.0:
            parts.append(f"💵 ≤${max_price_val:g}")
        partner_prefs = [p for p in (criteria_dict.get("partner_preference") or []) if p]
        if partner_prefs:
            parts.append(f"🏭 {', '.join(partner_prefs[:2])}{'…' if len(partner_prefs) > 2 else ''}")
        color_prefs = [c for c in (criteria_dict.get("color_preference") or []) if c]
        if color_prefs:
            parts.append(f"🎨 {', '.join(color_prefs[:2])}{'…' if len(color_prefs) > 2 else ''}")
        return " · ".join(parts)
    def _escape_table_cell(value) -> str:
        text = "" if value is None else str(value)
        text = text.replace("\r", " ").replace("\n", " ").strip()
        text = text.replace("|", "\\|")
        return text or "?"

    def _as_float(value, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def _color_names(colors) -> list:
        names = []
        for c in (colors or []):
            if not c:
                continue
            if isinstance(c, str):
                names.append(c.strip())
            elif isinstance(c, dict):
                n = (c.get("name") or "").strip()
                if n:
                    names.append(n)
        return [x for x in names if x]

    loc = criteria.get("location_preference", "")
    max_lead = criteria.get("max_lead_time", 999)
    print_pref = criteria.get("print_method", "")

    header_notes = []
    if validation_errors:
        header_notes.append("> Validation gate removed non-canonical fields before response generation.")

    # ── Compare product intent ──
    if intent == "compare_product":
        requested_count = _extract_requested_count(query)
        requested_count = requested_count if 0 < requested_count <= 4 else 0
        max_items = requested_count or 3
        norm_cp = compare_products[:max_items] if compare_products else [item.get("product", {}) for item in scores[:max_items]]
        if not norm_cp:
            return "❌ Không tìm thấy sản phẩm để so sánh. Vui lòng cung cấp tên/mã sản phẩm rõ ràng hơn."

        # Lấy scores từ state nếu có
        score_by_code = {}
        for item in scores:
            p = item.get("product", {})
            code = canonicalize_short_code(p.get("short_code"))
            if code:
                score_by_code[code] = item

        # Build comparison table
        filters_line = _format_filters(criteria)
        lines = [
            "## ⚖️ So sánh sản phẩm",
            "",
            f"Mình đang so sánh theo yêu cầu: *\"{query}\"*",
            (f"*Bộ lọc đang áp dụng:* {filters_line}" if filters_line else ""),
            "",
            "| Tiêu chí | " + " | ".join(
                f"**{_escape_table_cell(p.get('name', '?'))}**<br/><code>{_escape_table_cell(p.get('short_code', '?'))}</code>"
                for p in norm_cp
            ) + " |",
            "|---|---" + "|---" * (len(norm_cp) - 1) + "|",
        ]

        # Core attributes
        core_fields = [
            ("📍 Location", "location"),
            ("⏱️ Processing", "processing_time"),
            ("🧵 Material", "material"),
            ("🖨️ Print", "print_method"),
            ("📦 Inventory", "inventory_status"),
        ]

        for label, key in core_fields:
            values = []
            for p in norm_cp:
                val = p.get(key, "?")
                values.append(_escape_table_cell(val))
            lines.append(f"| {label} | " + " | ".join(values) + " |")

        # Partner comparison
        partner_lines = []
        for p in norm_cp:
            partners = p.get("partners", []) or []
            if partners:
                partner_str = ", ".join(sorted(partners)[:3])
                if len(partners) > 3:
                    partner_str += f" (+{len(partners)-3})"
            else:
                partner_str = "?"
            partner_lines.append(partner_str)
        lines.append(f"| 🏭 Partners | " + " | ".join(_escape_table_cell(p) for p in partner_lines) + " |")

        # Price comparison
        price_lines = []
        for p in norm_cp:
            price_min = _as_float(p.get("price_min", 0.0), 0.0)
            price_max = _as_float(p.get("price_max", 0.0), 0.0)
            if price_min == price_max:
                price_str = f"${price_min:.2f}"
            else:
                price_str = f"${price_min:.2f}–${price_max:.2f}"
            price_lines.append(price_str)
        lines.append(f"| 💵 Price Range | " + " | ".join(_escape_table_cell(p) for p in price_lines) + " |")

        # Colors comparison
        color_lines = []
        for p in norm_cp:
            colors_raw = p.get("available_colors", []) or []
            names = _color_names(colors_raw)
            if names:
                color_str = f"{len(names)} màu"
                sample = ", ".join(sorted(names)[:2])
                if sample:
                    color_str += f" ({sample})"
            else:
                color_str = "?"
            color_lines.append(color_str)
        lines.append(f"| 🎨 Colors | " + " | ".join(_escape_table_cell(c) for c in color_lines) + " |")

        # Score rows
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
                code = canonicalize_short_code(p.get("short_code"))
                item = score_by_code.get(code)
                if not item:
                    values.append("?")
                elif key == "score":
                    values.append(f"**{item.get('score', 0):.0f}**")
                else:
                    values.append(f"{item.get('breakdown', {}).get(key, 0):.0f}")
            lines.append(f"| {label} | " + " | ".join(_escape_table_cell(v) for v in values) + " |")

        lines.append("")

        # Winner conclusion
        if scores:
            winner = scores[0].get("product", {})
            winner_code = winner.get("short_code", "?")
            winner_name = winner.get("name", "?")
            lines.append(f"**🏆 Kết luận nhanh:** `{winner_code}` (**{winner_name}**) là lựa chọn nổi bật nhất theo điểm tổng.")
            lines.append("")
            lines.append("Nếu bạn muốn, mình có thể so sánh sâu hơn theo **giá**, **màu**, hoặc **partner** (vd: chỉ lấy partner Spire).")
        else:
            lines.append("**📊 So sánh dựa trên thông số cơ bản:**")
            lines.append("- **Location:** Địa điểm fulfillment")
            lines.append("- **Processing:** Thời gian xử lý")
            lines.append("- **Material:** Chất liệu sản phẩm")
            lines.append("- **Print Method:** Công nghệ in")
            lines.append("- **Partners:** Đối tác fulfillment")

        return "\n".join([x for x in lines if x != ""])

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

    list_all = criteria.get("list_all", False)
    requested_count = _extract_requested_count(query)
    requested_count = requested_count if 0 < requested_count <= 50 else 0
    filters_line = _format_filters(criteria)

    # Header theo query
    loc_label = f"thị trường **{loc}**" if loc else "nhu cầu của bạn"
    fast_label = f", giao hàng trong **≤{max_lead} ngày**" if max_lead < 999 else ""
    header = f"## 🔍 Gợi ý sản phẩm phù hợp cho {loc_label}{fast_label}\n\nMình vừa truy xuất catalog theo yêu cầu: *\"{query}\"*"
    if header_notes:
        header += "\n" + "\n".join(header_notes)
    if filters_line:
        header += f"\n\n*Bộ lọc đang áp dụng:* {filters_line}"
    header += "\n"

    # ── List All Mode: bảng markdown đầy đủ ──
    if list_all:
        lines = [
            header,
            f"*Tìm thấy **{len(scores)}** sản phẩm phù hợp, sắp xếp theo điểm score*",
            "",
            "| # | Tên sản phẩm | SKU | Score | Location | Processing | Print | Tồn kho | Giá bán đề xuất |",
            "|---|-------------|-----|-------|----------|------------|-------|---------|----------------|",
        ]
        for rank, item in enumerate(scores, 1):
            p = item["product"]
            score = item["score"]
            name = p.get('name', 'N/A')
            sku = p.get('short_code', 'N/A')
            loc_val = p.get('location', '?')
            proc = p.get('processing_time', '?')
            pm = p.get('print_method', '?')
            inv = p.get('inventory_status', 'unknown')
            price = p.get('suggested_selling_price', 0)
            inv_icon = '✅' if inv == 'available' else '❌' if inv == 'out_of_stock' else '❓'
            price_str = f"${price:.2f}" if price else '—'
            lines.append(
                f"| {rank} | **{name}** | `{sku}` | **{score:.0f}** | "
                f"{loc_val} | {proc} | {pm} | {inv_icon} {inv} | {price_str} |"
            )
        lines.append("")
        lines.append(f"💡 **Bạn muốn phân tích chi tiết sản phẩm nào?** Hỏi: `Phân tích chi tiết [tên SP]` hoặc `So sánh [SP1] với [SP2]`")
        return "\n".join(lines)

    if requested_count >= 4:
        n = min(requested_count, len(scores))
        lines = [
            header,
            f"*Mình chọn ra **{n}** sản phẩm đáng thử nhất (xếp theo score):*",
            "",
        ]
        for rank, item in enumerate(scores[:n], 1):
            p = item["product"]
            score = item["score"]
            name = p.get("name", "N/A")
            sku = p.get("short_code", "N/A")
            loc_val = p.get("location", "?")
            pm = p.get("print_method", "?")
            price = p.get("suggested_selling_price", 0)
            price_str = f"${price:.2f}" if price else "—"
            colors_cnt = p.get("colors_count", 0) or (len(p.get("available_colors") or []) if isinstance(p.get("available_colors"), list) else 0)
            partners_cnt = len(p.get("partners") or []) if isinstance(p.get("partners"), list) else 0
            meta = [f"{loc_val}", f"{pm}"]
            if colors_cnt:
                meta.append(f"{int(colors_cnt)} màu")
            if partners_cnt:
                meta.append(f"{partners_cnt} partner")
            meta_str = " · ".join(meta)
            lines.append(f"{rank}) **{name}** (`{sku}`) — **{score:.0f}/100**")
            lines.append(f"   - {meta_str} · Giá gợi ý: **{price_str}**")

        reason_section = ""
        if reasons:
            reason_section = "\n\n**✅ Lý do đề xuất sản phẩm #1:**\n" + "\n".join(f"- {r}" for r in reasons)

        cta = "\n\n💬 Bạn muốn mình ưu tiên **dòng rẻ dễ test** hay **dòng premium** trong list này? (Mình sẽ rút tiếp còn 5 mẫu phù hợp nhất)."
        return "\n".join(lines) + reason_section + cta

    # ── Top 3 Mode: card chi tiết (mặc định) ──
    product_lines = []
    for rank, item in enumerate(scores[:3], 1):
        p = item["product"]
        score = item["score"]
        medals = ["🥇", "🥈", "🥉"]
        medal = medals[rank - 1]
        product_lines.append(f"{medal} **{p.get('name', 'N/A')}** (`{p.get('short_code', 'N/A')}`) — **{score:.0f}/100**")
        product_lines.append(f"   - 📍 {p.get('location', '?')} · ⏱️ {p.get('processing_time', '?')} · 🖨️ {p.get('print_method', '?')}")
        product_lines.append(f"   - 💰 Giá gợi ý: **${p.get('suggested_selling_price', 0):.2f}** · Lợi nhuận/đơn: **${p.get('profit', 0):.2f}** · ROI: **{p.get('roi', 0):.0f}%**")
        product_lines.append(f"   - 🎯 Hợp với: **{p.get('recommended_audience', 'General Gift Buyers')}**")
        risks = p.get("risks") or []
        if risks:
            product_lines.append(f"   - ⚠️ Lưu ý: {', '.join(risks[:3])}")

    # Hiển thị số sản phẩm còn lại nếu có nhiều hơn 3
    more_section = ""
    if len(scores) > 3:
        more_section = f"\n\nNếu bạn muốn mình liệt kê nhiều hơn, cứ nhắn: **\"cho tôi 10 sản phẩm\"**, **\"cho tôi 15 sản phẩm\"** hoặc **\"list all\"**."

    # Lý do chọn #1
    reason_section = ""
    if reasons:
        reason_section = "\n\n**✅ Lý do đề xuất sản phẩm #1:**\n" + "\n".join(f"- {r}" for r in reasons)

    top_product = scores[0]["product"] if scores else {}
    partner_prices = top_product.get("partner_prices") if isinstance(top_product, dict) else {}
    partner_price_max = top_product.get("partner_price_max") if isinstance(top_product, dict) else {}
    partner_best_variant = top_product.get("partner_best_variant") if isinstance(top_product, dict) else {}

    max_price_constraint = _as_float(criteria.get("max_price", 9999.0), 9999.0)
    has_price_constraint = 0 < max_price_constraint < 9999.0

    best_partner = ""
    best_partner_price = None
    if isinstance(partner_prices, dict) and partner_prices:
        pairs = []
        for partner_name, partner_price in partner_prices.items():
            name = str(partner_name or "").strip()
            val = _as_float(partner_price, 0.0)
            if not name or val <= 0:
                continue
            pairs.append((name, val))
        pairs.sort(key=lambda x: x[1])
        if pairs:
            eligible = [x for x in pairs if (not has_price_constraint) or (x[1] <= max_price_constraint)]
            chosen = eligible[0] if eligible else pairs[0]
            best_partner, best_partner_price = chosen

    factory_section = ""
    if best_partner:
        sku_code = top_product.get("short_code", "N/A")
        partner_max = None
        if isinstance(partner_price_max, dict):
            partner_max_val = _as_float(partner_price_max.get(best_partner), 0.0)
            if partner_max_val > 0:
                partner_max = partner_max_val

        variant = None
        if isinstance(partner_best_variant, dict):
            v = partner_best_variant.get(best_partner)
            if isinstance(v, dict) and v:
                variant = v

        price_note = f"${best_partner_price:.2f}" if best_partner_price is not None else "—"
        range_note = ""
        if partner_max is not None and best_partner_price is not None and partner_max > (best_partner_price + 0.0001):
            range_note = f"${best_partner_price:.2f}–${partner_max:.2f}"

        lines = ["\n\n**🏭 Gợi ý xưởng & SKU (chốt nhanh):**", f"- Xưởng: **{best_partner}**"]

        if variant and best_partner_price is not None:
            variant_sku = (variant.get("sku") or "").strip()
            size = (variant.get("size") or "").strip()
            color = (variant.get("color") or "").strip()
            bits = []
            if size:
                bits.append(f"size **{size}**")
            if color:
                bits.append(f"màu **{color}**")
            variant_desc = ", ".join(bits) if bits else "biến thể rẻ nhất"
            lines.append(f"- Base cost (min): **{price_note}** ({variant_desc})")
            if range_note:
                lines.append(f"- Range theo xưởng: **{range_note}**")
            if variant_sku:
                lines.append(f"- Variant SKU: `{variant_sku}`")
        else:
            lines.append(f"- Base cost (min): **{price_note}**")
            if range_note:
                lines.append(f"- Range theo xưởng: **{range_note}**")

        lines.append(f"- Product SKU: `{sku_code}`")
        if range_note:
            lines.append("- Lưu ý: giá có thể tăng theo size/color (nên bạn có thể thấy mức cao hơn như $9.50 ở size lớn).")

        factory_section = "\n".join(lines)

    # CTA
    cta = "\n\n💬 Bạn muốn mình chốt **5 mẫu best-seller** theo hướng **giá rẻ dễ scale** hay **premium bán giá cao**?"

    return header + "\n".join(product_lines) + more_section + reason_section + factory_section + cta
