"""
LangGraph Nodes - Tất cả node functions của BurgerPrintsAgent
Dùng Gemini (langchain-google-genai) làm LLM
"""
import json
import os
import re
import logging
import queue
import threading
from typing import List

from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

_active_streams = {}
_streams_lock = threading.Lock()

def register_stream_queue(session_id: str, q: queue.Queue):
    with _streams_lock:
        _active_streams[session_id] = q

def unregister_stream_queue(session_id: str):
    with _streams_lock:
        _active_streams.pop(session_id, None)


from agent.graph.state import AgentState
from agent.services.api_knowledge import get_api_knowledge
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
API_KNOWLEDGE = get_api_knowledge()


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
    base_cost_max: float = Field(default=9999.0, description="Maximum acceptable base cost / cost price")
    base_cost_min: float = Field(default=0.0, description="Minimum acceptable base cost / cost price")
    selling_price_max: float = Field(default=9999.0, description="Maximum acceptable selling price")
    selling_price_min: float = Field(default=0.0, description="Minimum acceptable selling price")
    target_margin_min: float = Field(default=0.0, description="Minimum acceptable margin percentage")
    target_roi_min: float = Field(default=0.0, description="Minimum acceptable ROI percentage")
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


class PolishedResponseOutput(BaseModel):
    response: str = Field(
        description=(
            "Bản biên tập cuối cùng bằng tiếng Việt hoặc tiếng Anh, trình bày đẹp, chuyên nghiệp, "
            "không thay đổi dữ kiện, không bịa thêm SKU/giá/điểm số."
        )
    )


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

        system_prompt = f"""Bạn là AI assistant phân tích intent của seller POD (Print on Demand) trên nền tảng BurgerPrints.

{API_KNOWLEDGE}

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
- base_cost_max: giá vốn tối đa / chi phí tối đa
- base_cost_min: giá vốn tối thiểu
- selling_price_max: giá bán tối đa
- selling_price_min: giá bán tối thiểu
- target_margin_min: margin tối thiểu theo %
- target_roi_min: ROI tối thiểu theo %
- skus: danh sách mã SKU cụ thể
- list_all: true khi user muốn xem TOÀN BỘ danh sách ("toàn bộ", "tất cả", "danh sách đầy đủ", "liệt kê", "cho tôi hết", "all", "list all")

CÁC INTENT VÀ VÍ DỤ:
1. recommend_product:
   - "Tôi muốn bán áo thun cho thị trường Mỹ" → recommend_product, location_preference: US
   - "Tìm áo màu đen, partner Spire, dưới $12, ship US" → recommend_product, partner_preference: [Spire], color_preference: [black], max_price: 12.0, location_preference: US
   - "Tôi muốn bán T-shirt cho thị trường Mỹ, giá vốn dưới $8, ship dưới 5 ngày" → recommend_product, location_preference: US, base_cost_max: 8.0, max_lead_time: 5
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
                "base_cost_max": getattr(result, 'base_cost_max', 9999.0) or 9999.0,
                "base_cost_min": getattr(result, 'base_cost_min', 0.0) or 0.0,
                "selling_price_max": getattr(result, 'selling_price_max', 9999.0) or 9999.0,
                "selling_price_min": getattr(result, 'selling_price_min', 0.0) or 0.0,
                "target_margin_min": getattr(result, 'target_margin_min', 0.0) or 0.0,
                "target_roi_min": getattr(result, 'target_roi_min', 0.0) or 0.0,
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
        reasons.append(f"Sản xuất tại {loc}, phù hợp với thị trường mục tiêu.")
    if proc != "Unknown":
        reasons.append(f"Thời gian xử lý {proc}, hỗ trợ giao hàng tương đối nhanh.")
    if material != "Unknown":
        reasons.append(f"Chất liệu {material}, phù hợp với nhóm sản phẩm được đề xuất.")
    if pm != "Unknown":
        reasons.append(f"Công nghệ in {pm}, phổ biến và ổn định trong vận hành.")
    if breakdown:
        reasons.append(
            f"Điểm phù hợp thị trường đạt {breakdown.get('market_fit', 0):.0f}/100 "
            f"và điểm phù hợp mùa vụ đạt {breakdown.get('season_fit', 0):.0f}/100."
        )
        reasons.append(
            f"Điểm biên lợi nhuận đạt {breakdown.get('margin', 0):.0f}/100 "
            f"và điểm xu hướng đạt {breakdown.get('trend', 0):.0f}/100."
        )
    if product.get("recommended_audience"):
        reasons.append(f"Nhóm khách hàng phù hợp: {product.get('recommended_audience')}.")

    return reasons


def _translate_risk_text(risk: str) -> str:
    text = (risk or "").strip()
    if not text:
        return ""

    normalized = text.lower()
    if normalized == "high market saturation":
        return "Mức độ cạnh tranh trên thị trường đang ở mức cao."
    if normalized == "inventory freshness is unknown":
        return "Chưa có đủ dữ liệu để xác nhận độ cập nhật mới nhất của tồn kho."
    if normalized == "warm weather can reduce apparel demand":
        return "Điều kiện thời tiết nóng có thể làm giảm nhu cầu đối với nhóm sản phẩm này."
    if normalized == "no major risk from available signals":
        return "Chưa ghi nhận rủi ro đáng kể từ dữ liệu hiện có."

    weak_match = re.match(r"(.+?)\s+is weak for\s+(.+)", text, flags=re.IGNORECASE)
    if weak_match:
        season = weak_match.group(2).strip()
        return f"Mức độ phù hợp theo mùa hiện chưa cao trong giai đoạn {season}."

    text = text.replace("_", " ").strip(" .")
    if not text:
        return ""
    return text[0].upper() + text[1:] + "."


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
    """Create a deterministic response, then optionally polish it with LLM."""
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
    session_id = state.get("session_id", "")

    # Nếu đã có response_msg từ catalog_info, zorinask, hoặc create_order → bỏ qua
    if state.get("response_msg") and intent in ("create_order", "catalog_info", "general_inquiry"):
        if session_id:
            with _streams_lock:
                q = _active_streams.get(session_id)
            if q is not None:
                q.put(state.get("response_msg"))
        return state

    if error and not scores and intent != "create_order":
        err_msg = f"❌ Xin lỗi, đã xảy ra lỗi: {error}. Vui lòng thử lại sau."
        if session_id:
            with _streams_lock:
                q = _active_streams.get(session_id)
            if q is not None:
                q.put(err_msg)
        return {
            **state,
            "response_msg": err_msg,
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

    polished_response = _polish_response_with_llm(
        query=query,
        intent=intent,
        response=response,
        criteria=criteria,
        session_id=session_id,
    )

    if polished_response:
        response = polished_response

    return {**state, "response_msg": response}


def _polish_response_with_llm(
    query: str,
    intent: str,
    response: str,
    criteria: dict,
    session_id: str = "",
) -> str:
    """Use LLM as a final editorial layer without changing factual content."""
    if not response or intent not in {"recommend_product", "compare_product", "check_stock"}:
        if session_id:
            with _streams_lock:
                q = _active_streams.get(session_id)
            if q is not None:
                q.put(response)
        return response

    q = None
    if session_id:
        with _streams_lock:
            q = _active_streams.get(session_id)

    try:
        llm = _get_llm(temperature=0.05)
        criteria_text = json.dumps(criteria or {}, ensure_ascii=False)
        system_prompt = """Bạn là biên tập viên cao cấp chuyên chuẩn hóa phản hồi tư vấn sản phẩm POD cho khách hàng doanh nghiệp.

Mục tiêu:
- Biên tập lại phản hồi đầu vào thành một bản trình bày chuyên nghiệp, trang trọng, rõ ràng và có tính tư vấn.
- Chỉ được phép cải thiện cách diễn đạt, bố cục, tiêu đề, bullet, nhịp câu và markdown.
- Tuyệt đối không được thay đổi dữ kiện thực tế.

Nguyên tắc bất biến:
- Giữ nguyên toàn bộ tên sản phẩm, SKU, giá bán gợi ý, lợi nhuận, ROI, điểm số, thị trường, thời gian xử lý, công nghệ in và kết luận.
- Không bịa thêm sản phẩm, không thêm nhận định mới nếu đầu vào chưa có, không tự suy diễn.
- Không thay đổi thứ hạng sản phẩm.
- Không tự thêm phần thưởng, huy hiệu, slogan hoặc kết luận thừa.
- Không được để sót dữ kiện quan trọng đã xuất hiện trong đầu vào.

Chuẩn phong cách:
- Văn phong trang trọng, tự tin, gọn, đúng chính tả, phù hợp báo cáo tư vấn thương mại.
- Ưu tiên câu ngắn, rõ nghĩa, tránh kiểu nói hội thoại suồng sã.
- Markdown sạch, có tiêu đề hợp lý, khoảng cách dòng dễ đọc.
- Chỉ dùng emoji nếu thực sự cần; mặc định không dùng emoji.

Quy tắc trình bày bắt buộc:
- Với intent recommend_product:
  1. Một tiêu đề ngắn, chuyên nghiệp.
  2. Một đoạn mở đầu 1-2 câu nêu đã phân tích theo yêu cầu nào.
  3. Một mục danh sách sản phẩm đề xuất.
  4. Mỗi sản phẩm phải trình bày nhất quán theo các dòng: tên + SKU, điểm đánh giá, thông tin vận hành, tài chính, đối tượng phù hợp, lưu ý.
  5. Một mục kết luận hoặc cơ sở lựa chọn nếu đầu vào có dữ kiện tương ứng.
  6. Một câu kết ngắn nêu khả năng hỗ trợ tiếp nếu đầu vào có CTA.
- Với intent compare_product:
  1. Giữ bảng so sánh nếu bảng đã rõ ràng.
  2. Thêm mở đầu và kết luận ngắn gọn, không lan man.
- Với intent check_stock:
  1. Mở đầu ngắn.
  2. Danh sách trạng thái tồn kho hoặc sản phẩm thay thế rõ ràng.
  3. Kết thúc bằng câu hỗ trợ tiếp theo nếu phù hợp.

Quy tắc cấm:
- Không để tiêu đề treo, ví dụ như một dòng kiểu "Kết quả tốt nhất" nhưng không có nội dung theo sau.
- Không lặp lại cùng một ý bằng nhiều cách khác nhau.
- Không pha trộn quá nhiều kiểu bullet hoặc định dạng.
- Không biến kết quả thành quảng cáo khoa trương.
- Không chèn giải thích nội bộ như "dựa trên prompt", "theo mô hình", "tôi đã biên tập".

Yêu cầu đầu ra:
- Trả về duy nhất nội dung hoàn chỉnh. Không wrap JSON. Trả về text thô (markdown)."""

        human_prompt = (
            f"Intent: {intent}\n"
            f"Query người dùng: {query}\n"
            f"Tiêu chí đã trích xuất: {criteria_text}\n\n"
            "Hãy biên tập lại phản hồi sau theo đúng chuẩn tư vấn chuyên nghiệp, "
            "giữ nguyên dữ kiện nhưng nâng chất lượng trình bày lên mức cao hơn.\n\n"
            f"Phản hồi gốc cần biên tập lại:\n{response}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]

        if q is not None:
            chunks = []
            for chunk in llm.stream(messages):
                token = chunk.content
                chunks.append(token)
                q.put(token)
            polished = "".join(chunks).strip()
            return polished or response
        else:
            res = _invoke_with_retry(llm, messages)
            polished = (res.content or "").strip()
            return polished or response
    except Exception as e:
        logger.warning(f"LLM response polish failed: {e}")
        if q is not None:
            q.put(response)
        return response



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
            parts.append(f"Thị trường: {loc_val.upper()}")
        pm_val = (criteria_dict.get("print_method") or "").strip()
        if pm_val:
            parts.append(f"Công nghệ in: {pm_val}")
        max_lead_val = criteria_dict.get("max_lead_time", 999)
        if isinstance(max_lead_val, int) and 0 < max_lead_val < 999:
            parts.append(f"Thời gian xử lý: <={max_lead_val} ngày")
        base_cost_max_val = criteria_dict.get("base_cost_max", 9999.0)
        try:
            base_cost_max_val = float(base_cost_max_val)
        except Exception:
            base_cost_max_val = 9999.0
        if 0 < base_cost_max_val < 9999.0:
            parts.append(f"Giá vốn tối đa: ${base_cost_max_val:g}")
        selling_price_max_val = criteria_dict.get("selling_price_max", 9999.0)
        try:
            selling_price_max_val = float(selling_price_max_val)
        except Exception:
            selling_price_max_val = 9999.0
        if 0 < selling_price_max_val < 9999.0:
            parts.append(f"Giá bán tối đa: ${selling_price_max_val:g}")
        max_price_val = criteria_dict.get("max_price", 9999.0)
        try:
            max_price_val = float(max_price_val)
        except Exception:
            max_price_val = 9999.0
        if 0 < max_price_val < 9999.0 and base_cost_max_val >= 9999.0 and selling_price_max_val >= 9999.0:
            parts.append(f"Giá tối đa: ${max_price_val:g}")
        margin_min_val = criteria_dict.get("target_margin_min", 0.0)
        try:
            margin_min_val = float(margin_min_val)
        except Exception:
            margin_min_val = 0.0
        if margin_min_val > 0:
            parts.append(f"Margin tối thiểu: {margin_min_val:g}%")
        roi_min_val = criteria_dict.get("target_roi_min", 0.0)
        try:
            roi_min_val = float(roi_min_val)
        except Exception:
            roi_min_val = 0.0
        if roi_min_val > 0:
            parts.append(f"ROI tối thiểu: {roi_min_val:g}%")
        partner_prefs = [p for p in (criteria_dict.get("partner_preference") or []) if p]
        if partner_prefs:
            parts.append(f"Partner: {', '.join(partner_prefs[:2])}{'…' if len(partner_prefs) > 2 else ''}")
        color_prefs = [c for c in (criteria_dict.get("color_preference") or []) if c]
        if color_prefs:
            parts.append(f"Màu sắc: {', '.join(color_prefs[:2])}{'…' if len(color_prefs) > 2 else ''}")
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
    header_notes = []
    if validation_errors:
        header_notes.append("> Lưu ý: Hệ thống đã loại bỏ một số trường dữ liệu không hợp lệ trước khi tạo phản hồi.")

    # ── Compare product intent ──
    if intent == "compare_product":
        requested_count = _extract_requested_count(query)
        requested_count = requested_count if 0 < requested_count <= 4 else 0
        max_items = requested_count or 3
        norm_cp = compare_products[:max_items] if compare_products else [item.get("product", {}) for item in scores[:max_items]]
        if not norm_cp:
            return "Không tìm thấy sản phẩm để so sánh. Vui lòng cung cấp tên hoặc mã sản phẩm rõ ràng hơn."

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
            "## Bảng So Sánh Sản Phẩm",
            "",
            f"Yêu cầu đã tiếp nhận: *\"{query}\"*",
            (f"Tiêu chí đang áp dụng: {filters_line}" if filters_line else ""),
            "",
            "| Tiêu chí | " + " | ".join(
                f"**{_escape_table_cell(p.get('name', '?'))}**<br/><code>{_escape_table_cell(p.get('short_code', '?'))}</code>"
                for p in norm_cp
            ) + " |",
            "|---|---" + "|---" * (len(norm_cp) - 1) + "|",
        ]

        # Core attributes
        core_fields = [
            ("Khu vực", "location"),
            ("Thời gian xử lý", "processing_time"),
            ("Chất liệu", "material"),
            ("Công nghệ in", "print_method"),
            ("Tồn kho", "inventory_status"),
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
        lines.append(f"| Partner | " + " | ".join(_escape_table_cell(p) for p in partner_lines) + " |")

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
        lines.append(f"| Khoảng giá | " + " | ".join(_escape_table_cell(p) for p in price_lines) + " |")

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
        lines.append(f"| Màu sắc | " + " | ".join(_escape_table_cell(c) for c in color_lines) + " |")

        # Score rows
        score_fields = [
            ("Điểm tổng", "score"),
            ("Điểm xu hướng", "trend"),
            ("Độ phù hợp thị trường", "market_fit"),
            ("Độ phù hợp mùa vụ", "season_fit"),
            ("Điểm biên lợi nhuận", "margin"),
            ("Điểm cạnh tranh", "competition"),
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
            lines.append(f"**Kết luận:** `{winner_code}` ({winner_name}) là lựa chọn nổi bật nhất theo điểm đánh giá tổng hợp.")
            lines.append("")
            lines.append("Nếu cần, tôi có thể tiếp tục so sánh sâu hơn theo giá, màu sắc hoặc partner fulfilment.")
        else:
            lines.append("**Diễn giải tiêu chí so sánh:**")
            lines.append("- Location: Địa điểm fulfilment")
            lines.append("- Processing: Thời gian xử lý")
            lines.append("- Material: Chất liệu sản phẩm")
            lines.append("- Print Method: Công nghệ in")
            lines.append("- Partners: Đối tác fulfilment")

        return "\n".join([x for x in lines if x != ""])

    # ── Check stock intent ──
    if intent == "check_stock":
        alt_list = "\n".join(
            f"- {p.get('name','?')} (`{p.get('short_code','?')}`): {p.get('location','?')} | {p.get('processing_time','?')} | {p.get('inventory_status','unknown')}"
            for p in alternatives[:3]
        )
        oos_list = ", ".join(out_of_stock_ids[:10]) if out_of_stock_ids else "không xác định"
        return (
            f"## Kết Quả Kiểm Tra Tồn Kho\n\n"
            f"Đã hoàn tất kiểm tra catalog BurgerPrints.\n\n"
            f"- Danh sách mã đang hết hàng: {oos_list}\n\n"
            + (f"**Sản phẩm thay thế đề xuất:**\n{alt_list}" if alt_list else "Không tìm thấy sản phẩm thay thế phù hợp.")
            + "\n\nNếu cần, tôi có thể tiếp tục phân tích chi tiết từng sản phẩm thay thế."
        )

    # ── Recommend product intent (default) ──
    if not scores:
        return "Không tìm thấy sản phẩm phù hợp với yêu cầu hiện tại. Vui lòng thử lại với tiêu chí khác."

    list_all = criteria.get("list_all", False)
    requested_count = _extract_requested_count(query)
    requested_count = requested_count if 0 < requested_count <= 50 else 0
    filters_line = _format_filters(criteria)

    # Header theo query
    loc_label = f"thị trường {loc}" if loc else "nhu cầu hiện tại"
    fast_label = f", thời gian xử lý không vượt quá {max_lead} ngày" if max_lead < 999 else ""
    header = f"## Đề Xuất Sản Phẩm Phù Hợp Cho {loc_label}{fast_label}\n\nYêu cầu đã tiếp nhận: *\"{query}\"*"
    if header_notes:
        header += "\n" + "\n".join(header_notes)
    if filters_line:
        header += f"\n\nTiêu chí đang áp dụng: {filters_line}"
    header += "\n"

    # ── List All Mode: bảng markdown đầy đủ ──
    if list_all:
        lines = [
            header,
            f"Tìm thấy **{len(scores)}** sản phẩm phù hợp, đã sắp xếp theo điểm đánh giá tổng hợp.",
            "",
            "| STT | Tên sản phẩm | SKU | Điểm | Khu vực | Xử lý | In ấn | Tồn kho | Giá bán gợi ý |",
            "|---|---|---|---|---|---|---|---|---|",
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
            price_str = f"${price:.2f}" if price else '—'
            lines.append(
                f"| {rank} | **{name}** | `{sku}` | **{score:.0f}** | "
                f"{loc_val} | {proc} | {pm} | {inv} | {price_str} |"
            )
        lines.append("")
        lines.append("Nếu cần, tôi có thể phân tích chi tiết từng sản phẩm hoặc so sánh trực tiếp giữa hai mã cụ thể.")
        return "\n".join(lines)

    if requested_count >= 4:
        n = min(requested_count, len(scores))
        lines = [
            header,
            f"Dưới đây là **{n}** sản phẩm phù hợp nhất, được xếp theo điểm đánh giá tổng hợp:",
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
            lines.append(f"{rank}. **{name}** (`{sku}`)")
            lines.append(f"- Điểm đánh giá: **{score:.0f}/100**")
            lines.append(f"- Thông tin chính: {meta_str}")
            lines.append(f"- Giá bán gợi ý: **{price_str}**")
            lines.append("")

        reason_section = ""
        if reasons:
            reason_section = "\n**Cơ Sở Đề Xuất Sản Phẩm Đứng Đầu:**\n" + "\n".join(f"- {r}" for r in reasons)

        cta = "\n\nNếu cần, tôi có thể tiếp tục rút gọn danh sách xuống 5 mẫu theo định hướng giá phổ thông dễ mở rộng hoặc phân khúc premium."
        return "\n".join(lines) + reason_section + cta

    # ── Top 3 Mode: card chi tiết (mặc định) ──
    product_lines = ["", "**Danh Sách Đề Xuất Hàng Đầu:**", ""]
    for rank, item in enumerate(scores[:3], 1):
        p = item["product"]
        score = item["score"]
        product_lines.append(f"{rank}. **{p.get('name', 'N/A')}** (`{p.get('short_code', 'N/A')}`)")
        product_lines.append(f"- Điểm đánh giá: **{score:.0f}/100**")
        product_lines.append(
            f"- Thông tin vận hành: {p.get('location', '?')} | {p.get('processing_time', '?')} | {p.get('print_method', '?')}"
        )
        product_lines.append(
            f"- Giá bán gợi ý: **${p.get('suggested_selling_price', 0):.2f}** | "
            f"Lợi nhuận ước tính: **${p.get('profit', 0):.2f}/đơn** | ROI: **{p.get('roi', 0):.0f}%**"
        )
        product_lines.append(f"- Tệp khách hàng phù hợp: **{p.get('recommended_audience', 'General Gift Buyers')}**")
        risks = p.get("risks") or []
        if risks:
            risk_texts = []
            for risk in risks[:3]:
                translated = _translate_risk_text(risk)
                if translated:
                    risk_texts.append(translated)
            if risk_texts:
                product_lines.append(f"- Lưu ý: {' '.join(risk_texts)}")
        product_lines.append("")

    # Hiển thị số sản phẩm còn lại nếu có nhiều hơn 3
    more_section = ""
    if len(scores) > 3:
        more_section = (
            "\nNếu cần mở rộng danh sách, bạn có thể yêu cầu thêm theo các lựa chọn như "
            "`cho tôi 10 sản phẩm`, `cho tôi 15 sản phẩm` hoặc `list all`."
        )

    # Lý do chọn #1
    reason_section = ""
    if reasons:
        reason_section = "\n**Cơ Sở Đề Xuất Sản Phẩm Đứng Đầu:**\n" + "\n".join(f"- {r}" for r in reasons)

    top_product = scores[0]["product"] if scores else {}
    partner_prices = top_product.get("partner_prices") if isinstance(top_product, dict) else {}
    partner_price_max = top_product.get("partner_price_max") if isinstance(top_product, dict) else {}
    partner_best_variant = top_product.get("partner_best_variant") if isinstance(top_product, dict) else {}
    partner_summary = top_product.get("partner_summary") if isinstance(top_product, dict) else []

    max_price_constraint = _as_float(criteria.get("base_cost_max", criteria.get("max_price", 9999.0)), 9999.0)
    has_price_constraint = 0 < max_price_constraint < 9999.0

    best_partner = ""
    best_partner_price = None
    selected_partner_summary = None
    if isinstance(partner_summary, list) and partner_summary:
        ranked_rows = []
        for row in partner_summary:
            if not isinstance(row, dict):
                continue
            name = str(row.get("partner") or "").strip()
            price_min = _as_float(row.get("price_min"), 0.0)
            color_count = int(row.get("color_count", 0) or 0)
            if not name or price_min <= 0:
                continue
            ranked_rows.append((name, price_min, color_count, row))
        ranked_rows.sort(key=lambda item: (-item[2], item[1], item[0]))
        if ranked_rows:
            eligible = [x for x in ranked_rows if (not has_price_constraint) or (x[1] <= max_price_constraint)]
            chosen = eligible[0] if eligible else ranked_rows[0]
            best_partner, best_partner_price, _, selected_partner_summary = chosen
    if isinstance(partner_prices, dict) and partner_prices:
        pairs = []
        for partner_name, partner_price in partner_prices.items():
            name = str(partner_name or "").strip()
            val = _as_float(partner_price, 0.0)
            if not name or val <= 0:
                continue
            pairs.append((name, val))
        pairs.sort(key=lambda x: x[1])
        if pairs and not best_partner:
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
        if selected_partner_summary is None and isinstance(partner_summary, list):
            for row in partner_summary:
                if isinstance(row, dict) and str(row.get("partner") or "").strip() == best_partner:
                    selected_partner_summary = row
                    break

        price_note = f"${best_partner_price:.2f}" if best_partner_price is not None else "—"
        range_note = ""
        if partner_max is not None and best_partner_price is not None and partner_max > (best_partner_price + 0.0001):
            range_note = f"${best_partner_price:.2f}–${partner_max:.2f}"

        lines = ["\n**Gợi Ý Partner Fulfilment:**", f"- Partner đề xuất: **{best_partner}**"]

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
            lines.append(f"- Giá gốc tối thiểu: **{price_note}** ({variant_desc})")
            if range_note:
                lines.append(f"- Khoảng giá theo partner: **{range_note}**")
            if variant_sku:
                lines.append(f"- Mã biến thể: `{variant_sku}`")
        else:
            lines.append(f"- Giá gốc tối thiểu: **{price_note}**")
            if range_note:
                lines.append(f"- Khoảng giá theo partner: **{range_note}**")

        lines.append(f"- Mã sản phẩm: `{sku_code}`")
        if range_note:
            lines.append("- Lưu ý: giá có thể thay đổi theo size hoặc màu sắc.")

        if isinstance(selected_partner_summary, dict):
            color_count = int(selected_partner_summary.get("color_count", 0) or 0)
            size_count = int(selected_partner_summary.get("size_count", 0) or 0)
            markets = [str(x).strip() for x in (selected_partner_summary.get("markets") or []) if str(x).strip()]
            if color_count > 0:
                lines.append(f"- Supported colors: **{color_count}**")
            if size_count > 0:
                lines.append(f"- Supported sizes: **{size_count}**")
            if markets:
                lines.append(f"- Served market/location: **{', '.join(markets)}**")
        factory_section = "\n".join(lines)

    # CTA
    cta = (
        "\n\nNếu cần, tôi có thể tiếp tục chọn lọc 5 mẫu tiềm năng nhất theo một trong hai định hướng: "
        "**giá phổ thông dễ mở rộng** hoặc **phân khúc premium giá trị cao**."
    )

    return header + "\n".join(product_lines) + more_section + reason_section + factory_section + cta
