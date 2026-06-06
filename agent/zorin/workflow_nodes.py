from __future__ import annotations

from typing import Any, Dict

from agent.graph.state import AgentState
from agent.graph.nodes import (
    compare_node,
    decision_engine_node,
    demand_analysis_node,
    generate_response_node,
    inventory_analysis_node,
    market_analysis_node,
    persona_compatibility_node,
    pricing_profit_node,
    season_weather_node,
    suggest_alternatives_node,
    validate_output_node,
)
from agent.zorin.data_agent import DataAgent
from agent.zorin.memory import MemoryManager

import logging
logger = logging.getLogger(__name__)

_memory = MemoryManager()
_data_agent = DataAgent()
_intent_analyzer = None
_task_router = None
_ask = None
_catalog_responder = None


def _get_intent_analyzer():
    global _intent_analyzer
    if _intent_analyzer is None:
        from agent.zorin.info_manager import IntentAnalyzer
        _intent_analyzer = IntentAnalyzer()
    return _intent_analyzer


def _get_task_router():
    global _task_router
    if _task_router is None:
        from agent.zorin.info_manager import TaskRouter
        _task_router = TaskRouter()
    return _task_router


def _get_ask():
    global _ask
    if _ask is None:
        from agent.zorin.info_manager import ZorinAsk
        _ask = ZorinAsk()
    return _ask


def _get_catalog_responder():
    global _catalog_responder
    if _catalog_responder is None:
        from agent.zorin.info_manager import CatalogInfoResponder
        _catalog_responder = CatalogInfoResponder()
    return _catalog_responder


# ---------------------------------------------------------------------------
# Brain node
# ---------------------------------------------------------------------------

def zorin_brain_node(state: AgentState) -> AgentState:
    query = (state.get("query") or "").strip()
    session_id = (state.get("session_id") or "").strip()
    if not query:
        return {**state, "error": "Query không được để trống", "response_msg": "Query không được để trống"}
    if session_id:
        history = _memory.get_history(session_id=session_id, limit=20)
        _memory.save_message(session_id=session_id, role="user", content=query)
    else:
        history = state.get("conversation_history", []) or []
    return {**state, "conversation_history": history, "error": ""}


# ---------------------------------------------------------------------------
# Intent analysis node
# ---------------------------------------------------------------------------

def intent_analysis_node(state: AgentState) -> AgentState:
    query = state.get("query", "")
    history = state.get("conversation_history", []) or []
    result = _get_intent_analyzer().analyze(query=query, history=history)
    return {
        **state,
        "intent": result.get("intent", ""),
        "extracted_criteria": result.get("extracted_criteria", {}) or {},
        "error": result.get("error", "") or "",
    }


# ---------------------------------------------------------------------------
# Task router node
# ---------------------------------------------------------------------------

def task_router_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "") or "recommend_product"
    criteria = state.get("extracted_criteria", {}) or {}
    query = state.get("query", "")
    routed = _get_task_router().route(intent=intent, criteria=criteria, query=query)
    return {
        **state,
        "zorin_route": routed.get("route", "data_agent"),
        "missing_fields": routed.get("missing_fields", []) or [],
        "task": routed.get("task", intent),
    }


def route_after_task_router(state: AgentState) -> str:
    return state.get("zorin_route", "data_agent")


# ---------------------------------------------------------------------------
# Zorin ask node (missing fields / general inquiry)
# ---------------------------------------------------------------------------

def zorin_ask_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "") or state.get("task", "")
    missing_fields = state.get("missing_fields", []) or []
    query = state.get("query", "")

    # Nếu là general_inquiry → dùng LLM để trả lời thông minh hơn
    if intent == "general_inquiry" and not missing_fields:
        try:
            response = _get_ask().respond(query=query)
            return {**state, "response_msg": response}
        except Exception as e:
            logger.warning(f"ZorinAsk.respond failed: {e}")

    # Nếu thiếu field → build clarification message
    message = _get_ask().build_message(intent=intent, missing_fields=missing_fields)
    return {**state, "response_msg": message}


# ---------------------------------------------------------------------------
# Data agent node
# ---------------------------------------------------------------------------

def data_agent_node(state: AgentState) -> AgentState:
    task = state.get("task", "") or state.get("intent", "")
    criteria = state.get("extracted_criteria", {}) or {}

    if task == "compare_product":
        payload = _data_agent.fetch_compare_products(criteria.get("product_names", []) or [])
    else:
        # recommend_product, check_stock, create_order, catalog_info → tất cả cần catalog
        payload = _data_agent.fetch_catalog(limit=500)

    stock_payload = _data_agent.fetch_out_of_stock()
    return {**state, **payload, **stock_payload}


# ---------------------------------------------------------------------------
# Function node - xử lý theo task
# ---------------------------------------------------------------------------

def function_node(state: AgentState) -> AgentState:
    task = state.get("task", "") or state.get("intent", "")

    # --- Compare products ---
    if task == "compare_product":
        state = compare_node(state)
        state = market_analysis_node(state)
        state = inventory_analysis_node(state)
        state = season_weather_node(state)
        state = demand_analysis_node(state)
        state = pricing_profit_node(state)
        state = persona_compatibility_node(state)
        return decision_engine_node(state)

    # --- Check stock ---
    if task == "check_stock":
        state = market_analysis_node(state)
        state = inventory_analysis_node(state)
        return suggest_alternatives_node(state)

    # --- Create order ---
    if task == "create_order":
        missing = state.get("missing_fields", []) or []
        if missing:
            return zorin_ask_node(state)
        # Nếu đủ thông tin → hướng dẫn tạo đơn qua modal UI
        criteria = state.get("extracted_criteria", {}) or {}
        product_names = criteria.get("product_names", [])
        product_str = ", ".join(product_names) if product_names else "sản phẩm đã chọn"
        return {
            **state,
            "response_msg": (
                f"✅ Mình đã nhận yêu cầu tạo đơn cho **{product_str}**.\n\n"
                "Để tạo đơn hàng an toàn, hãy dùng nút **📦 Tạo đơn** xuất hiện bên trên câu trả lời.\n\n"
                "Bạn cần cung cấp:\n"
                "- **SKU sản phẩm** (ví dụ: USG5000)\n"
                "- **Kích thước** (S, M, L, XL, ...)\n"
                "- **Tên và địa chỉ** người nhận hàng\n\n"
                "Mình sẽ validate SKU trong catalog trước khi gửi lên BurgerPrints API."
            ),
        }

    # --- Catalog info: trả lời thông tin về catalog ---
    if task == "catalog_info":
        return _handle_catalog_info(state)

    # --- Recommend product (default) ---
    state = market_analysis_node(state)
    state = inventory_analysis_node(state)
    state = season_weather_node(state)
    state = demand_analysis_node(state)
    state = pricing_profit_node(state)
    state = persona_compatibility_node(state)

    # Apply filters từ criteria
    state = _apply_criteria_filters(state)

    return decision_engine_node(state)


def _handle_catalog_info(state: AgentState) -> AgentState:
    """Xử lý catalog_info intent - trả lời thông tin catalog thực từ API"""
    criteria = state.get("extracted_criteria", {}) or {}
    catalog_query_type = criteria.get("catalog_query_type", "general") or "general"
    query = state.get("query", "")
    products_norm = state.get("products_norm", []) or []

    # Nếu chưa có products_norm, dùng products_raw để normalize
    if not products_norm:
        from agent.services.html_parser import normalize_product
        products_raw = state.get("products_raw", []) or []
        products_norm = [normalize_product(p) for p in products_raw]

    try:
        responder = _get_catalog_responder()
        response = responder.build_response(
            query_type=catalog_query_type,
            products_norm=products_norm,
            query=query,
        )
        scores = state.get("scores", []) or []
        if not scores:
            terms = _extract_catalog_focus_terms(query)
            if terms:
                matched = []
                for p in products_norm:
                    name = (p.get("name") or "").lower()
                    if name and all(t in name for t in terms):
                        matched.append(p)
                if matched:
                    scores = [{"product": p, "score": 0, "breakdown": {}, "evidence": {}} for p in matched]

        return {**state, "response_msg": response, "scores": scores}
    except Exception as e:
        logger.error(f"CatalogInfoResponder error: {e}")
        return {
            **state,
            "response_msg": f"❌ Không thể lấy thông tin catalog: {e}. Vui lòng thử lại.",
        }


def _extract_catalog_focus_terms(query: str) -> list:
    q = (query or "").lower()
    if "crewneck" in q and "sweatshirt" in q:
        return ["crewneck", "sweatshirt"]
    if "sweatshirt" in q:
        return ["sweatshirt"]
    if "hoodie" in q:
        return ["hoodie"]
    return []


def _apply_criteria_filters(state: AgentState) -> AgentState:
    """
    Lọc candidates theo criteria người dùng (partner, color, price, location, print_method)
    TRƯỚC KHI chạy decision engine để chỉ rank những sản phẩm phù hợp criteria.
    """
    criteria = state.get("extracted_criteria", {}) or {}
    candidates = state.get("candidates") or state.get("products_norm", []) or []

    if not candidates:
        return state

    filtered = list(candidates)
    original_count = len(filtered)

    q = (state.get("query") or "").lower()

    def _infer_location_pref() -> str:
        loc_pref_raw = (criteria.get("location_preference") or "").strip()
        if loc_pref_raw:
            return loc_pref_raw
        if any(x in q for x in ["thị trường mỹ", "thi truong my", "us", "usa", "united states", "mỹ", "my"]):
            return "US"
        if any(x in q for x in ["thị trường eu", "eu", "europe"]):
            return "EU"
        if "china" in q or "trung quốc" in q:
            return "China"
        if "vietnam" in q or "việt nam" in q or "viet nam" in q:
            return "Vietnam"
        return ""

    def _is_tshirt_query() -> bool:
        if any(x in q for x in ["áo thun", "ao thun", "t-shirt", "tshirt", "tee"]):
            return True
        for pn in (criteria.get("product_names") or []):
            if any(x in (pn or "").lower() for x in ["t-shirt", "tshirt", "tee", "áo thun", "ao thun"]):
                return True
        return False

    # Filter theo location
    loc_pref = _infer_location_pref().strip().upper()
    if loc_pref:
        loc_filtered = [
            p for p in filtered
            if _loc_match(p.get("location", ""), loc_pref)
        ]
        if loc_filtered:
            filtered = loc_filtered
            logger.info(f"[Filter] location={loc_pref}: {original_count} → {len(filtered)}")

    if _is_tshirt_query():
        include_terms = ["t-shirt", "tshirt", "tee"]
        exclude_terms = ["hoodie", "sweatshirt", "crewneck", "tank", "long sleeve", "raglan", "polo", "mug", "poster", "tote", "bag", "cap", "hat", "beanie", "jogger", "pant", "short"]
        tshirt_filtered = []
        for p in filtered:
            name = (p.get("name") or "").lower()
            if not name:
                continue
            if any(t in name for t in exclude_terms):
                continue
            if any(t in name for t in include_terms):
                tshirt_filtered.append(p)
        if tshirt_filtered:
            filtered = tshirt_filtered
            logger.info(f"[Filter] type=tshirt: → {len(filtered)}")

    product_names = [x for x in (criteria.get("product_names") or []) if x]
    if product_names and len(product_names) == 1 and any(x in q for x in ["phân tích", "phan tich", "chi tiết", "chi tiet", "kỹ hơn", "ky hon"]):
        token = (product_names[0] or "").strip().lower()
        if token:
            specific = [
                p for p in filtered
                if token in (p.get("name", "") or "").lower()
                or token in (p.get("short_code", "") or "").lower()
            ]
            if specific:
                filtered = specific
                logger.info(f"[Filter] product_name={product_names[0]}: → {len(filtered)}")

    # Filter theo partner
    partner_prefs = [p.strip() for p in (criteria.get("partner_preference") or []) if p]
    if partner_prefs:
        pref_lower = [p.lower() for p in partner_prefs]
        partner_filtered = [
            p for p in filtered
            if any(
                any(pp in (partner_name or "").lower() for pp in pref_lower)
                for partner_name in (p.get("partners") or [])
            )
        ]
        if partner_filtered:
            filtered = partner_filtered
            logger.info(f"[Filter] partners={partner_prefs}: → {len(filtered)}")

    # Filter theo color
    color_prefs = [c.strip().lower() for c in (criteria.get("color_preference") or []) if c]
    if color_prefs:
        color_filtered = [
            p for p in filtered
            if any(
                any(
                    cp in (
                        ((col.get("name") or "") if isinstance(col, dict) else (col or ""))
                    ).lower()
                    for cp in color_prefs
                )
                for col in (p.get("available_colors") or [])
            )
        ]
        if color_filtered:
            filtered = color_filtered
            logger.info(f"[Filter] colors={color_prefs}: → {len(filtered)}")

    # Filter theo max_price
    max_price = criteria.get("max_price", 9999.0) or 9999.0
    if max_price < 9999.0:
        price_filtered = [
            p for p in filtered
            if (p.get("price_min") or p.get("base_cost") or 0) <= max_price
        ]
        if price_filtered:
            filtered = price_filtered
            logger.info(f"[Filter] max_price=${max_price}: → {len(filtered)}")

    # Filter theo min_price
    min_price = criteria.get("min_price", 0.0) or 0.0
    if min_price > 0.0:
        price_filtered = [
            p for p in filtered
            if (p.get("price_min") or p.get("base_cost") or 0) >= min_price
        ]
        if price_filtered:
            filtered = price_filtered

    # Filter theo print_method
    print_pref = (criteria.get("print_method") or criteria.get("print_tech") or "").strip().upper()
    if print_pref:
        pm_filtered = [
            p for p in filtered
            if print_pref in (p.get("print_method") or "").upper()
        ]
        if pm_filtered:
            filtered = pm_filtered
            logger.info(f"[Filter] print_method={print_pref}: → {len(filtered)}")

    # Filter theo max_lead_time
    max_lead = criteria.get("max_lead_time", 999) or 999
    if max_lead < 999:
        lead_filtered = [
            p for p in filtered
            if (p.get("processing_min") or 999) <= max_lead
        ]
        if lead_filtered:
            filtered = lead_filtered
            logger.info(f"[Filter] max_lead_time={max_lead}: → {len(filtered)}")

    logger.info(f"[Filter] Total: {original_count} → {len(filtered)} candidates after criteria filter")

    return {
        **state,
        "candidates": filtered,
        "products_norm": filtered,
    }


def _loc_match(product_loc: str, pref: str) -> bool:
    """So sánh location của product với preference"""
    loc = (product_loc or "").upper()
    if pref == "US":
        return loc in ("US", "USA", "UNITED STATES")
    if pref == "EU":
        return loc in ("EU", "EUROPE", "POLAND", "GERMANY", "NETHERLANDS", "UK")
    if pref == "CHINA":
        return loc == "CHINA"
    if pref == "VIETNAM" or pref == "VN":
        return loc in ("VIETNAM", "VN")
    return loc == pref


# ---------------------------------------------------------------------------
# Output node
# ---------------------------------------------------------------------------

def output_node(state: AgentState) -> AgentState:
    # Nếu đã có response_msg (từ zorinask, catalog_info, order) → không generate lại
    if state.get("response_msg") and state.get("zorin_route") == "zorinask":
        return state
    if state.get("task") == "create_order" and state.get("response_msg"):
        return state
    if state.get("task") == "catalog_info" and state.get("response_msg"):
        return state
    state = validate_output_node(state)
    return generate_response_node(state)


# ---------------------------------------------------------------------------
# Memory manager node
# ---------------------------------------------------------------------------

def memory_manager_node(state: AgentState) -> AgentState:
    session_id = (state.get("session_id") or "").strip()
    if not session_id:
        return state

    response_msg = state.get("response_msg", "") or ""
    intent = state.get("intent", "") or ""
    metadata: Dict[str, Any] = {
        "scores": state.get("scores", [])[:5],
        "reasons": state.get("reasons", []),
        "winner": state.get("winner") or {},
        "alternatives": state.get("alternatives", [])[:3],
        "validation_errors": state.get("validation_errors", []),
    }
    _memory.save_message(
        session_id=session_id,
        role="assistant",
        content=response_msg,
        intent=intent,
        metadata=metadata,
    )
    return state
