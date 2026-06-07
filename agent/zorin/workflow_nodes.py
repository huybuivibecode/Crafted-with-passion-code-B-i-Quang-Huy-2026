from __future__ import annotations

from typing import Any, Dict, List

import json
import re
from pathlib import Path

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
from agent.services.commerce_intel import infer_category
from agent.zorin.data_agent import DataAgent
from agent.zorin.memory import MemoryManager
from agent.zorin.object_store import SessionObjectStore

import logging
logger = logging.getLogger(__name__)

_memory = MemoryManager()
_data_agent = DataAgent()
_object_store = SessionObjectStore()
_intent_analyzer = None
_task_router = None
_ask = None
_catalog_responder = None
_offline_detail_index = None
_response_localizer = None

_FOLLOWUP_REFERENCE_TOKENS = (
    "mẫu này",
    "san pham nay",
    "sản phẩm này",
    "sản phẩm đó",
    "san pham do",
    "mẫu đó",
    "cái này",
    "cái đó",
    "mau nay",
    "mau do",
    "this product",
    "that product",
    "these products",
    "those products",
    "this one",
    "that one",
    "the one above",
    "vừa rồi",
    "ở trên",
    "ở dưới",
    "o tren",
    "o duoi",
)

_GENERIC_PRODUCT_TOKENS = (
    "áo",
    "ao",
    "áo thun",
    "ao thun",
    "t-shirt",
    "tshirt",
    "tee",
    "hoodie",
    "sweatshirt",
    "tank top",
    "tanktop",
    "mug",
    "poster",
    "tote",
    "bag",
)


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


def _get_followup_resolver():
    from agent.zorin.info_manager import FollowUpResolver
    return FollowUpResolver


def _get_context_task_refiner():
    from agent.zorin.info_manager import ContextTaskRefiner
    return ContextTaskRefiner


def _get_other_task_manager():
    from agent.zorin.info_manager import OtherTaskManager
    return OtherTaskManager


def _get_flow_validator():
    from agent.zorin.info_manager import FlowValidator
    return FlowValidator


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


def _get_response_localizer():
    global _response_localizer
    if _response_localizer is None:
        from agent.zorin.info_manager import ResponseLocalizer
        _response_localizer = ResponseLocalizer()
    return _response_localizer


def _localize_response_for_query(query: str, text: str) -> str:
    raw_text = str(text or "").strip()
    if not raw_text:
        return raw_text
    return _get_response_localizer().localize(query=query, text=raw_text)


def _normalize_query_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _has_followup_reference(query: str) -> bool:
    normalized = _normalize_query_text(query)
    return any(token in normalized for token in _FOLLOWUP_REFERENCE_TOKENS)


def _looks_like_structured_recommendation_query(query: str, criteria: Dict[str, Any]) -> bool:
    normalized = _normalize_query_text(query)
    criteria = criteria or {}

    max_price = criteria.get("max_price", 9999.0)
    max_lead_time = criteria.get("max_lead_time", 999)
    has_budget = False
    has_lead_time = False
    try:
        has_budget = 0 < float(max_price) < 9999.0
    except Exception:
        has_budget = False
    try:
        has_lead_time = 0 < int(max_lead_time) < 999
    except Exception:
        has_lead_time = False

    has_market = bool((criteria.get("location_preference") or criteria.get("market") or "").strip())
    has_product_type = any(token in normalized for token in _GENERIC_PRODUCT_TOKENS)
    asks_for_choice = any(
        token in normalized
        for token in ("chọn partner", "partner nào", "sku nào", "gợi ý", "tìm", "nên chọn", "chon partner")
    )
    has_selection_constraints = has_market or has_budget or has_lead_time or bool(criteria.get("partner_preference"))

    return has_product_type and asks_for_choice and has_selection_constraints


def _has_specific_product_reference(criteria: Dict[str, Any]) -> bool:
    criteria = criteria or {}
    skus = [str(x).strip() for x in (criteria.get("skus") or []) if str(x).strip()]
    if skus:
        return True

    product_names = [str(x).strip() for x in (criteria.get("product_names") or []) if str(x).strip()]
    if not product_names:
        return False

    for name in product_names:
        lowered = _normalize_query_text(name)
        if re.search(r"\d", lowered):
            return True
        if all(token not in lowered for token in _GENERIC_PRODUCT_TOKENS):
            return True
    return False


def _build_returned_objects_payload(state: AgentState) -> List[dict]:
    objects: List[dict] = []
    seen = set()

    def _push(product: dict, source: str) -> None:
        if not isinstance(product, dict) or not product:
            return
        key = str(product.get("short_code") or product.get("id") or product.get("name") or "").strip().upper()
        if not key or key in seen:
            return
        seen.add(key)
        objects.append({
            "source": source,
            "product": _product_brief(product),
        })

    for item in (state.get("scores", []) or [])[:12]:
        if isinstance(item, dict):
            _push(item.get("product", {}), "scores")

    _push(state.get("winner") or {}, "winner")

    for product in (state.get("alternatives", []) or [])[:8]:
        _push(product, "alternatives")

    for product in (state.get("compare_products", []) or [])[:8]:
        _push(product, "compare_products")

    return objects


def _build_object_store_snapshot(state: AgentState) -> Dict[str, Any]:
    return {
        "query": state.get("query", ""),
        "intent": state.get("intent", ""),
        "task": state.get("task", ""),
        "returned_objects": _build_returned_objects_payload(state),
        "winner": _product_brief(state.get("winner") or {}) if isinstance(state.get("winner"), dict) else {},
        "applied_filters": list(state.get("applied_filters", []) or []),
        "inventory_snapshot": dict(state.get("inventory_snapshot", {}) or {}),
    }


def _extract_recent_products_from_history(history: List[dict]) -> List[dict]:
    recent_products: List[dict] = []
    seen_codes = set()

    for msg in reversed(history or []):
        if msg.get("role") != "assistant":
            continue
        metadata = msg.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue

        buckets = []
        scores = metadata.get("scores") or []
        if isinstance(scores, list):
            for item in scores:
                if isinstance(item, dict):
                    product = item.get("product", {}) if isinstance(item.get("product"), dict) else {}
                    if product:
                        buckets.append(product)

        winner = metadata.get("winner")
        if isinstance(winner, dict) and winner:
            buckets.append(winner)

        alternatives = metadata.get("alternatives") or []
        if isinstance(alternatives, list):
            for item in alternatives:
                if isinstance(item, dict) and item:
                    buckets.append(item)

        for product in buckets:
            code = str(product.get("short_code") or product.get("id") or "").strip().upper()
            name = str(product.get("name") or "").strip()
            dedupe_key = code or name.lower()
            if not dedupe_key or dedupe_key in seen_codes:
                continue
            seen_codes.add(dedupe_key)
            recent_products.append(product)

        if recent_products:
            break

    return recent_products


def _resolve_followup_context(
    *,
    query: str,
    intent: str,
    criteria: Dict[str, Any],
    history: List[dict],
) -> Dict[str, Any]:
    criteria = dict(criteria or {})
    current_names = [x for x in (criteria.get("product_names") or []) if x]
    current_skus = [x for x in (criteria.get("skus") or []) if x]
    needs_compare_resolution = intent == "compare_product" and len(current_names) < 2 and len(current_skus) < 2
    needs_single_resolution = (
        intent in {"check_stock", "recommend_product", "catalog_info"} and not current_names and not current_skus
    )

    if not (needs_compare_resolution or needs_single_resolution):
        return criteria

    if not _has_followup_reference(query):
        # Query tự thân đầy đủ tiêu chí thì không được kéo context sản phẩm từ lượt trước.
        return criteria

    recent_products = _extract_recent_products_from_history(history)
    if not recent_products:
        return criteria

    resolution = _get_followup_resolver().resolve(
        query=query,
        intent=intent,
        criteria=criteria,
        recent_products=recent_products[:5],
        history=history,
    )
    if not resolution.get("should_resolve"):
        return criteria

    selected_indices = [
        idx for idx in (resolution.get("selected_indices") or [])
        if isinstance(idx, int) and 1 <= idx <= len(recent_products)
    ]
    if not selected_indices:
        return criteria

    picked = [recent_products[idx - 1] for idx in selected_indices]

    if len(picked) < 1 or (needs_compare_resolution and len(picked) < 2):
        return criteria

    existing_name_keys = {str(x).strip().lower() for x in current_names if x}
    existing_skus = {str(x).strip().upper() for x in current_skus if x}

    for product in picked:
        name = str(product.get("name") or "").strip()
        code = str(product.get("short_code") or product.get("id") or "").strip().upper()
        if name and name.lower() not in existing_name_keys:
            current_names.append(name)
            existing_name_keys.add(name.lower())
        if code and code not in existing_skus:
            current_skus.append(code)
            existing_skus.add(code)

    criteria["product_names"] = current_names
    criteria["skus"] = current_skus
    criteria["resolved_from_history"] = True
    criteria["resolved_reference_query"] = query
    criteria["resolved_reference_reason"] = resolution.get("reason", "")
    logger.info(
        "[FollowUp] Resolved from history for intent=%s with %s products via LLM",
        intent,
        len(picked),
    )
    return criteria


def _refine_task_with_product_context(
    *,
    query: str,
    intent: str,
    criteria: Dict[str, Any],
    history: List[dict],
) -> Dict[str, Any]:
    criteria = dict(criteria or {})
    if not criteria:
        return criteria
    if not (criteria.get("resolved_from_history") or _has_specific_product_reference(criteria)):
        return criteria
    if intent == "recommend_product" and _looks_like_structured_recommendation_query(query, criteria):
        return criteria

    refinement = _get_context_task_refiner().refine(
        query=query,
        intent=intent,
        criteria=criteria,
        history=history,
    )
    if refinement.get("should_override") and refinement.get("task"):
        criteria["task_override"] = refinement.get("task")
        criteria["task_override_reason"] = refinement.get("reason", "")
        logger.info(
            "[ContextTask] Override task=%s for intent=%s",
            criteria["task_override"],
            intent,
        )
    return criteria


def _route_open_task_to_other(
    *,
    query: str,
    intent: str,
    criteria: Dict[str, Any],
    history: List[dict],
) -> Dict[str, Any]:
    criteria = dict(criteria or {})
    if intent == "recommend_product" and _looks_like_structured_recommendation_query(query, criteria):
        return criteria
    decision = _get_other_task_manager().should_route_to_other(
        query=query,
        intent=intent,
        criteria=criteria,
        history=history,
    )
    if decision.get("use_other"):
        criteria["task_override"] = "other"
        criteria["task_override_reason"] = decision.get("reason", "")
        logger.info("[OtherTask] Override task=other for intent=%s", intent)
    return criteria


def _dedupe_list(items: List[Any]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for item in items or []:
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _append_validation_report(
    state: AgentState,
    *,
    phase: str,
    passed: bool,
    task: str,
    reason: str,
    missing_information: List[str] | None = None,
) -> List[dict]:
    reports = list(state.get("validation_reports", []) or [])
    reports.append({
        "phase": phase,
        "passed": bool(passed),
        "task": task,
        "reason": reason,
        "missing_information": list(missing_information or []),
        "retry_count": int(state.get("retry_count", 0) or 0),
    })
    return reports


def _append_reflection_trace(
    state: AgentState,
    *,
    phase: str,
    from_task: str,
    to_task: str,
    next_route: str,
    validator_reason: str,
    reflection_reason: str,
    missing_information: List[str] | None = None,
) -> List[dict]:
    trace = list(state.get("reflection_trace", []) or [])
    trace.append({
        "phase": phase,
        "from_task": from_task,
        "to_task": to_task,
        "next_route": next_route,
        "validator_reason": validator_reason,
        "reflection_reason": reflection_reason,
        "missing_information": list(missing_information or []),
        "retry_count": int(state.get("retry_count", 0) or 0) + 1,
    })
    return trace


def _build_validator_clarification_message(
    *,
    query: str,
    reports: List[dict],
    missing_information: List[str] | None = None,
) -> str:
    missing_information = [str(x).strip() for x in (missing_information or []) if str(x).strip()]
    latest_reason = ""
    for report in reversed(reports or []):
        reason = str((report or {}).get("reason") or "").strip()
        if reason:
            latest_reason = reason
            break

    lines = [
        "Mình đã kiểm tra lại nhiều lần nhưng vẫn chưa xác định chắc chắn luồng xử lý phù hợp cho yêu cầu này.",
    ]
    if latest_reason:
        lines += ["", f"- Lý do gần nhất: {latest_reason}"]
    if missing_information:
        pretty = ", ".join(missing_information)
        lines += ["", f"- Cần bạn làm rõ thêm: {pretty}"]
    lines += [
        "",
        f"- Yêu cầu hiện tại: {query}",
        "",
        "Bạn hãy nói rõ hơn sản phẩm, phạm vi dữ liệu hoặc kiểu phân tích bạn muốn để mình chọn đúng luồng xử lý.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Brain node
# ---------------------------------------------------------------------------

def zorin_brain_node(state: AgentState) -> AgentState:
    query = (state.get("query") or "").strip()
    session_id = (state.get("session_id") or "").strip()
    object_snapshot = {}
    if not query:
        return {**state, "error": "Query không được để trống", "response_msg": "Query không được để trống"}
    if session_id:
        history = _memory.get_history(session_id=session_id, limit=20)
        object_snapshot = _object_store.get_snapshot(session_id=session_id)
        _memory.save_message(session_id=session_id, role="user", content=query)
    else:
        history = state.get("conversation_history", []) or []
    return {
        **state,
        "conversation_history": history,
        "object_store_snapshot": object_snapshot,
        "returned_objects": list(object_snapshot.get("returned_objects", []) or []),
        "error": "",
        "response_msg": "",
        "missing_fields": [],
        "task": "",
        "zorin_route": "",
        "applied_filters": [],
        "task_replan_reason": "",
        "replanned_task": "",
        "replanned_route": "",
        "validator_reason": "",
        "validator_missing_information": [],
        "reflection_trace": [],
        "retry_count": 0,
        "max_retry_count": 3,
        "validation_reports": [],
        "validator_next": "",
    }


# ---------------------------------------------------------------------------
# Intent analysis node
# ---------------------------------------------------------------------------

def intent_analysis_node(state: AgentState) -> AgentState:
    query = state.get("query", "")
    history = state.get("conversation_history", []) or []
    result = _get_intent_analyzer().analyze(query=query, history=history)
    criteria = _resolve_followup_context(
        query=query,
        intent=result.get("intent", ""),
        criteria=result.get("extracted_criteria", {}) or {},
        history=history,
    )
    criteria = _refine_task_with_product_context(
        query=query,
        intent=result.get("intent", ""),
        criteria=criteria,
        history=history,
    )
    criteria = _route_open_task_to_other(
        query=query,
        intent=result.get("intent", ""),
        criteria=criteria,
        history=history,
    )
    return {
        **state,
        "intent": result.get("intent", ""),
        "extracted_criteria": criteria,
        "error": result.get("error", "") or "",
    }


# ---------------------------------------------------------------------------
# Task router node
# ---------------------------------------------------------------------------

def task_router_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "") or "recommend_product"
    criteria = state.get("extracted_criteria", {}) or {}
    query = state.get("query", "")
    history = state.get("conversation_history", []) or []
    routed = _get_task_router().route(
        intent=intent,
        criteria=criteria,
        query=query,
        history=history,
        preferred_task=state.get("replanned_task", "") or "",
        preferred_route=state.get("replanned_route", "") or "",
    )
    return {
        **state,
        "zorin_route": routed.get("route", "data_agent"),
        "missing_fields": routed.get("missing_fields", []) or [],
        "task": routed.get("task", intent),
        "task_replan_reason": routed.get("replan_reason", "") or "",
        "replanned_task": "",
        "replanned_route": "",
    }


def route_after_task_router(state: AgentState) -> str:
    return state.get("zorin_route", "data_agent")


def routing_validator_node(state: AgentState) -> AgentState:
    query = state.get("query", "")
    intent = state.get("intent", "") or ""
    task = state.get("task", "") or intent
    route = state.get("zorin_route", "data_agent")
    criteria = state.get("extracted_criteria", {}) or {}
    history = state.get("conversation_history", []) or []
    missing_fields = state.get("missing_fields", []) or []
    retry_count = int(state.get("retry_count", 0) or 0)
    max_retry_count = int(state.get("max_retry_count", 3) or 3)

    decision = _get_flow_validator().validate_routing(
        query=query,
        intent=intent,
        task=task,
        route=route,
        criteria=criteria,
        missing_fields=missing_fields,
        history=history,
    )
    validator_reason = decision.get("reason", "")
    validator_missing_information = decision.get("missing_information", [])
    reports = _append_validation_report(
        state,
        phase="routing",
        passed=bool(decision.get("is_valid", True)),
        task=task,
        reason=validator_reason,
        missing_information=validator_missing_information,
    )

    if decision.get("is_valid", True):
        return {
            **state,
            "validation_reports": reports,
            "validator_reason": "",
            "validator_missing_information": [],
            "validator_next": route,
        }

    next_retry = retry_count + 1
    if next_retry > max_retry_count:
        clarification = _build_validator_clarification_message(
            query=query,
            reports=reports,
            missing_information=validator_missing_information,
        )
        return {
            **state,
            "retry_count": next_retry,
            "validation_reports": reports,
            "validator_reason": validator_reason,
            "validator_missing_information": validator_missing_information,
            "response_msg": _localize_response_for_query(query, clarification),
            "validator_next": "memory",
        }

    replanned = _get_flow_validator().replan_task(
        query=query,
        intent=intent,
        current_task=task,
        current_route=route,
        criteria=criteria,
        history=history,
        validation_reason=validator_reason,
        missing_information=validator_missing_information,
    )
    next_task = (replanned.get("task") or task or intent).strip()
    next_route = (replanned.get("route") or "").strip() or "task_router"
    reflection_reason = replanned.get("reason", "") or validator_reason
    reflections = _append_reflection_trace(
        state,
        phase="routing",
        from_task=task,
        to_task=next_task,
        next_route=next_route,
        validator_reason=validator_reason,
        reflection_reason=reflection_reason,
        missing_information=validator_missing_information,
    )
    logger.info("[RoutingValidator] Retry #%s via reflection: %s -> %s", next_retry, task, next_task)
    return {
        **state,
        "retry_count": next_retry,
        "validation_reports": reports,
        "task_replan_reason": reflection_reason,
        "replanned_task": next_task,
        "replanned_route": next_route if next_route in {"data_agent", "zorinask", "memory"} else "",
        "validator_reason": validator_reason,
        "validator_missing_information": validator_missing_information,
        "reflection_trace": reflections,
        "response_msg": "",
        "validator_next": next_route if next_route in {"task_router", "zorinask", "data_agent", "memory"} else "task_router",
    }


def route_after_routing_validator(state: AgentState) -> str:
    return state.get("validator_next", "data_agent")


# ---------------------------------------------------------------------------
# Zorin ask node (missing fields / general inquiry)
# ---------------------------------------------------------------------------

def zorin_ask_node(state: AgentState) -> AgentState:
    intent = state.get("task", "") or state.get("intent", "")
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
        # recommend_product, check_stock, create_order, catalog_info, other → tất cả cần catalog
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

    # --- Product partner info: thông tin xưởng/partner của sản phẩm hiện tại ---
    if task == "product_partner_info":
        return _handle_product_partner_info(state)

    # --- Product detail info: thông tin chi tiết của sản phẩm hiện tại ---
    if task == "product_detail_info":
        return _handle_product_detail_info(state)

    # --- Other: fallback task có LLM planner + data access ---
    if task == "other":
        return _handle_other_task(state)

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
    state = decision_engine_node(state)
    winner = state.get("winner")
    if isinstance(winner, dict) and winner:
        enriched_winner = _enrich_product_with_partner_summary(dict(winner))
        scores = list(state.get("scores", []) or [])
        if scores and isinstance(scores[0], dict):
            scores[0] = {**scores[0], "product": enriched_winner}
        state = {
            **state,
            "winner": enriched_winner,
            "scores": scores,
        }
    return state


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


def _handle_product_detail_info(state: AgentState) -> AgentState:
    target = _find_target_product(state)
    if not target:
        return {
            **state,
            "response_msg": "Mình chưa xác định được sản phẩm cụ thể. Bạn hãy nhắc lại tên sản phẩm hoặc SKU để mình lấy thông tin chi tiết.",
        }

    _enrich_candidates_with_offline_details([target])
    _enrich_product_with_partner_summary(target)

    short_code = str(target.get("short_code") or target.get("id") or "").strip().upper()
    variations = _data_agent.fetch_filtered_variations(short_code) if short_code else []

    colors = []
    sizes = []
    variation_count = 0

    raw_colors = target.get("available_colors") or []
    if isinstance(raw_colors, list):
        colors.extend(str(x).strip() for x in raw_colors if str(x).strip())

    raw_sizes = target.get("available_sizes") or []
    if isinstance(raw_sizes, list):
        sizes.extend(str(x).strip() for x in raw_sizes if str(x).strip())

    if variations:
        variation_count = len([v for v in variations if isinstance(v, dict)])
        for item in variations:
            if not isinstance(item, dict):
                continue
            color = str(item.get("color") or "").strip()
            size = str(item.get("size") or "").strip()
            if color:
                colors.append(color)
            if size:
                sizes.append(size)

    colors = sorted({c for c in colors if c}, key=lambda x: x.lower())
    sizes = sorted({s for s in sizes if s}, key=lambda x: x.lower())

    price_min = target.get("price_min") or target.get("base_cost") or 0
    price_max = target.get("price_max") or price_min or 0

    try:
        price_min = float(price_min) if price_min not in (None, "") else 0.0
    except Exception:
        price_min = 0.0
    try:
        price_max = float(price_max) if price_max not in (None, "") else price_min
    except Exception:
        price_max = price_min

    lines = [
        f"Thông tin chi tiết sản phẩm {target.get('name', short_code or 'đã chọn')}",
        "",
        f"- SKU sản phẩm: {short_code or 'N/A'}",
        f"- Khu vực sản xuất: {target.get('location', 'Unknown')}",
        f"- Thời gian xử lý: {target.get('processing_time', 'Unknown')}",
        f"- Công nghệ in: {target.get('print_method', 'Unknown')}",
        f"- Chất liệu: {target.get('material', 'Unknown')}",
    ]

    if price_min > 0:
        if price_max > price_min:
            lines.append(f"- Giá gốc tham khảo: ${price_min:.2f} - ${price_max:.2f}")
        else:
            lines.append(f"- Giá gốc tham khảo: ${price_min:.2f}")

    if colors:
        preview_colors = ", ".join(colors[:15])
        if len(colors) > 15:
            preview_colors += f" và {len(colors) - 15} màu khác"
        lines.append(f"- Màu sắc khả dụng: {preview_colors}")
    else:
        lines.append("- Màu sắc khả dụng: Chưa có dữ liệu chi tiết")

    if sizes:
        lines.append(f"- Kích thước khả dụng: {', '.join(sizes)}")
    else:
        lines.append("- Kích thước khả dụng: Chưa có dữ liệu chi tiết")

    if variation_count:
        lines.append(f"- Số biến thể đã kiểm tra: {variation_count}")

    lines += [
        "",
        "Nếu cần, mình có thể kiểm tra tiếp xưởng sản xuất, biến thể rẻ nhất hoặc so sánh sản phẩm này với một mẫu khác.",
    ]

    target["available_colors"] = colors
    target["available_sizes"] = sizes

    return {
        **state,
        "scores": [{"product": target, "score": 0, "breakdown": {}, "evidence": {}}],
        "winner": target,
        "response_msg": "\n".join(lines),
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


def _clean_lookup_token(text: str) -> str:
    chars = [ch.lower() for ch in str(text or "") if ch.isalnum()]
    return "".join(chars)


def _find_target_product(state: AgentState) -> dict:
    criteria = state.get("extracted_criteria", {}) or {}
    catalog_index = state.get("catalog_index", {}) or {}
    products_norm = state.get("products_norm", []) or []
    by_short_code = catalog_index.get("by_short_code", {}) or {}

    for sku in (criteria.get("skus") or []):
        code = str(sku or "").strip().upper()
        if code and code in by_short_code:
            return {**by_short_code[code]}

    wanted_names = [_clean_lookup_token(x) for x in (criteria.get("product_names") or []) if x]
    if not wanted_names:
        return {}

    best = {}
    best_score = -1
    for product in products_norm:
        name = _clean_lookup_token(product.get("name", ""))
        code = _clean_lookup_token(product.get("short_code") or product.get("id") or "")
        if not name and not code:
            continue
        for token in wanted_names:
            score = 0
            if token and token == code:
                score += 1000
            if token and token in code:
                score += 700
            if token and token == name:
                score += 500
            if token and token in name:
                score += 350
            if score > best_score:
                best_score = score
                best = product

    return {**best} if best_score > 0 and isinstance(best, dict) else {}


def _handle_product_partner_info(state: AgentState) -> AgentState:
    criteria = state.get("extracted_criteria", {}) or {}
    target = _find_target_product(state)
    if not target:
        return {
            **state,
            "response_msg": "Mình chưa xác định được sản phẩm cụ thể để lấy thông tin xưởng. Bạn hãy nhắc lại tên sản phẩm hoặc SKU.",
        }

    _enrich_candidates_with_offline_details([target])
    _enrich_product_with_partner_summary(target)

    short_code = str(target.get("short_code") or target.get("id") or "").strip().upper()
    variations = _data_agent.fetch_filtered_variations(short_code) if short_code else []

    partner_prices = dict(target.get("partner_prices") or {})
    partner_price_max = dict(target.get("partner_price_max") or {})
    partner_best_variant = dict(target.get("partner_best_variant") or {})
    partner_summary_map = {
        str(item.get("partner") or "").strip(): item
        for item in (target.get("partner_summary") or [])
        if isinstance(item, dict) and str(item.get("partner") or "").strip()
    }
    partners = list(target.get("partners") or [])

    if variations:
        for item in variations:
            if not isinstance(item, dict):
                continue
            partner_name = str(item.get("partner_name") or item.get("partner") or "").strip()
            if not partner_name:
                continue
            if partner_name not in partners:
                partners.append(partner_name)
            try:
                price = float(item.get("price")) if item.get("price") not in (None, "") else None
            except Exception:
                price = None
            if price is not None:
                current_min = partner_prices.get(partner_name)
                partner_prices[partner_name] = price if current_min is None else min(current_min, price)
                current_max = partner_price_max.get(partner_name)
                partner_price_max[partner_name] = price if current_max is None else max(current_max, price)
                if current_min is None or price <= current_min:
                    partner_best_variant[partner_name] = {
                        "price": float(price),
                        "sku": item.get("sku"),
                        "size": item.get("size"),
                        "color": item.get("color"),
                    }

    if not partners:
        return {
            **state,
            "scores": [{"product": target, "score": 0, "breakdown": {}, "evidence": {}}],
            "winner": target,
            "response_msg": (
                f"Thông tin xưởng của sản phẩm {target.get('name', short_code or 'đã chọn')} hiện chưa có đủ dữ liệu chi tiết. "
                "Bạn có thể thử lại sau hoặc hỏi theo SKU cụ thể để mình kiểm tra sâu hơn."
            ),
        }

    lines = [
        f"Thông tin xưởng của sản phẩm {target.get('name', short_code or 'đã chọn')}",
        "",
        f"- SKU sản phẩm: {short_code or 'N/A'}",
        f"- Khu vực sản xuất: {target.get('location', 'Unknown')}",
        f"- Thời gian xử lý: {target.get('processing_time', 'Unknown')}",
        f"- Số xưởng hoặc partner khả dụng: {len(partners)}",
        "",
        "Danh sách xưởng khả dụng",
    ]

    for idx, partner_name in enumerate(sorted(partners), 1):
        min_price = partner_prices.get(partner_name)
        max_price = partner_price_max.get(partner_name)
        variant = partner_best_variant.get(partner_name) if isinstance(partner_best_variant, dict) else None
        bullet = f"- {idx}. {partner_name}"
        if min_price is not None:
            if max_price is not None and max_price > min_price:
                bullet += f" | Giá gốc: ${min_price:.2f} - ${max_price:.2f}"
            else:
                bullet += f" | Giá gốc từ: ${min_price:.2f}"
        if isinstance(variant, dict):
            variant_bits = []
            if variant.get("size"):
                variant_bits.append(f"size {variant.get('size')}")
            if variant.get("color"):
                variant_bits.append(f"màu {variant.get('color')}")
            if variant_bits:
                bullet += f" | Biến thể rẻ nhất: {', '.join(variant_bits)}"
        summary = partner_summary_map.get(partner_name, {})
        color_count = int(summary.get("color_count", 0) or 0) if isinstance(summary, dict) else 0
        size_count = int(summary.get("size_count", 0) or 0) if isinstance(summary, dict) else 0
        markets = summary.get("markets") or [] if isinstance(summary, dict) else []
        if color_count > 0:
            bullet += f" | {color_count} màu"
        if size_count > 0:
            bullet += f" | {size_count} size"
        if markets:
            bullet += f" | phục vụ: {', '.join(markets)}"
        lines.append(bullet)

    lines += [
        "",
        "Nếu cần, mình có thể so sánh các xưởng này theo giá gốc, màu sắc hoặc biến thể rẻ nhất.",
    ]

    target["partners"] = sorted(partners)
    target["partner_prices"] = partner_prices
    target["partner_price_max"] = partner_price_max
    target["partner_best_variant"] = partner_best_variant

    return {
        **state,
        "scores": [{"product": target, "score": 0, "breakdown": {}, "evidence": {}}],
        "winner": target,
        "response_msg": "\n".join(lines),
    }


def _product_brief(product: dict) -> dict:
    if not isinstance(product, dict):
        return {}
    return {
        "name": product.get("name"),
        "short_code": product.get("short_code") or product.get("id"),
        "location": product.get("location"),
        "processing_time": product.get("processing_time"),
        "print_method": product.get("print_method"),
        "price_min": product.get("price_min"),
        "price_max": product.get("price_max"),
        "partners": product.get("partners"),
    }


def _variation_brief(variation: dict) -> dict:
    if not isinstance(variation, dict):
        return {}
    return {
        "partner_name": variation.get("partner_name") or variation.get("partner"),
        "sku": variation.get("sku"),
        "size": variation.get("size"),
        "color": variation.get("color"),
        "price": variation.get("price"),
    }


def _build_catalog_summary(products_norm: List[dict]) -> dict:
    summary: dict[str, Any] = {
        "total_products": len(products_norm or []),
        "locations": [],
        "print_methods": [],
        "partners": [],
    }
    if not products_norm:
        return summary

    def _top_values(values: List[str], limit: int = 8) -> List[str]:
        counts: Dict[str, int] = {}
        for value in values:
            key = str(value or "").strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return [name for name, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

    summary["locations"] = _top_values([p.get("location", "") for p in products_norm])
    summary["print_methods"] = _top_values([p.get("print_method", "") for p in products_norm])
    partners: List[str] = []
    for product in products_norm:
        raw_partners = product.get("partners") or []
        if isinstance(raw_partners, list):
            partners.extend(str(x) for x in raw_partners if x)
        elif product.get("partner"):
            partners.append(str(product.get("partner")))
    summary["partners"] = _top_values(partners)
    return summary


def _collect_focus_products(state: AgentState, target: dict | None = None, limit: int = 6) -> List[dict]:
    products_norm = state.get("products_norm", []) or []
    criteria = state.get("extracted_criteria", {}) or {}
    scores = state.get("scores", []) or []
    collected: List[dict] = []
    seen = set()

    def _add(product: dict) -> None:
        if not isinstance(product, dict):
            return
        key = str(product.get("short_code") or product.get("id") or product.get("name") or "").strip().upper()
        if not key or key in seen:
            return
        seen.add(key)
        collected.append(product)

    if target:
        _add(target)

    for item in scores:
        product = item.get("product") if isinstance(item, dict) else None
        if isinstance(product, dict):
            _add(product)
        if len(collected) >= limit:
            break

    wanted_names = [str(x).lower() for x in (criteria.get("product_names") or []) if x]
    wanted_skus = {str(x).strip().upper() for x in (criteria.get("skus") or []) if x}
    for product in products_norm:
        name = str(product.get("name") or "").lower()
        sku = str(product.get("short_code") or product.get("id") or "").strip().upper()
        if sku and sku in wanted_skus:
            _add(product)
        elif any(token and token in name for token in wanted_names):
            _add(product)
        if len(collected) >= limit:
            break

    if len(collected) < limit:
        for product in _extract_recent_products_from_history(state.get("conversation_history", []) or []):
            _add(product)
            if len(collected) >= limit:
                break

    return [_product_brief(product) for product in collected[:limit]]


def _handle_other_task(state: AgentState) -> AgentState:
    query = state.get("query", "")
    intent = state.get("intent", "") or "other"
    criteria = dict(state.get("extracted_criteria", {}) or {})
    history = state.get("conversation_history", []) or []
    products_norm = state.get("products_norm", []) or []
    target = _find_target_product(state)
    catalog_summary = _build_catalog_summary(products_norm)
    focus_products = _collect_focus_products(state, target=target)

    planner = _get_other_task_manager().plan(
        query=query,
        intent=intent,
        criteria=criteria,
        history=history,
        target_product=_product_brief(target) if target else {},
        focus_products=focus_products,
        catalog_summary=catalog_summary,
    )

    target_names = [x for x in (criteria.get("product_names") or []) if x]
    target_skus = [x for x in (criteria.get("skus") or []) if x]
    for name in planner.get("target_product_names", []) or []:
        if name and name not in target_names:
            target_names.append(name)
    for sku in planner.get("target_skus", []) or []:
        code = str(sku).strip().upper()
        if code and code not in target_skus:
            target_skus.append(code)
    criteria["product_names"] = target_names
    criteria["skus"] = target_skus

    extra_data: Dict[str, Any] = {
        "planner_action": planner.get("action", ""),
        "planner_reason": planner.get("reason", ""),
        "answer_goal": planner.get("answer_goal", ""),
    }
    enriched_target = target

    if planner.get("action") == "fetch_variations_then_answer":
        lookup_state = {**state, "extracted_criteria": criteria}
        enriched_target = _find_target_product(lookup_state) or target
        short_code = str((enriched_target or {}).get("short_code") or (enriched_target or {}).get("id") or "").strip().upper()
        if short_code:
            variations = _data_agent.fetch_filtered_variations(
                short_code,
                partner=((criteria.get("partner_preference") or [None])[0]),
                color=((criteria.get("color_preference") or [None])[0]),
                max_price=criteria.get("max_price"),
                min_price=criteria.get("min_price"),
            )
            extra_data["variations"] = [_variation_brief(item) for item in variations[:40]]
            extra_data["variation_count"] = len(variations)
            extra_data["variation_short_code"] = short_code

    elif planner.get("action") == "fetch_compare_details_then_answer":
        compare_names = [x for x in target_names if x][:4]
        if compare_names:
            compare_payload = _data_agent.fetch_compare_products(compare_names)
            compare_products = compare_payload.get("compare_products", []) or []
            extra_data["compare_products"] = [_product_brief(product) for product in compare_products[:4]]
            extra_data["compare_count"] = len(compare_products)

    response = _get_other_task_manager().respond(
        query=query,
        intent=intent,
        criteria=criteria,
        history=history,
        catalog_summary=catalog_summary,
        focus_products=focus_products,
        target_product=_product_brief(enriched_target) if enriched_target else {},
        extra_data=extra_data,
    )

    return {
        **state,
        "extracted_criteria": criteria,
        "response_msg": response.get("response", "") or "Mình chưa thể hoàn tất yêu cầu này.",
        "winner": enriched_target or state.get("winner"),
    }


def _get_offline_detail_index() -> Dict[str, Dict[str, Any]]:
    global _offline_detail_index
    if isinstance(_offline_detail_index, dict):
        return _offline_detail_index

    path = Path(__file__).resolve().parents[2] / "datajson" / "product_details.json"
    if not path.exists():
        _offline_detail_index = {}
        return _offline_detail_index

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _offline_detail_index = {}
        return _offline_detail_index

    items = payload.get("result", []) if isinstance(payload, dict) else []
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        short_code = (item.get("short_code") or "").strip().upper()
        if not short_code:
            continue
        if item.get("status") != 200:
            continue
        body = item.get("data", {}) if isinstance(item.get("data"), dict) else {}
        data = body.get("data", body)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data.get("data")
        variations = data.get("variations") if isinstance(data, dict) else None
        if not isinstance(variations, list) or not variations:
            continue
        min_price = None
        max_price = None
        partner_prices: Dict[str, float] = {}
        partner_max_prices: Dict[str, float] = {}
        partner_best_variant: Dict[str, Dict[str, Any]] = {}
        partners = set()
        for v in variations:
            if not isinstance(v, dict):
                continue
            pn = (v.get("partner_name") or "").strip()
            if pn:
                partners.add(pn)
            try:
                price = float(v.get("price")) if v.get("price") not in (None, "") else None
            except Exception:
                price = None
            if price is None:
                continue
            min_price = price if min_price is None else min(min_price, price)
            max_price = price if max_price is None else max(max_price, price)
            if pn:
                prev = partner_prices.get(pn)
                partner_prices[pn] = price if prev is None else min(prev, price)
                prev_max = partner_max_prices.get(pn)
                partner_max_prices[pn] = price if prev_max is None else max(prev_max, price)
                if (prev is None) or (price <= prev):
                    partner_best_variant[pn] = {
                        "price": float(price),
                        "sku": v.get("sku"),
                        "size": v.get("size"),
                        "color": v.get("color"),
                        "color_hex": v.get("color_hex"),
                    }
        if min_price is None:
            continue
        index[short_code] = {
            "price_min": float(min_price),
            "price_max": float(max_price) if max_price is not None else float(min_price),
            "partner_prices": {k: float(v) for k, v in partner_prices.items()},
            "partner_price_max": {k: float(v) for k, v in partner_max_prices.items()},
            "partner_best_variant": partner_best_variant,
            "partners": sorted(partners),
        }

    _offline_detail_index = index
    return _offline_detail_index


def _enrich_candidates_with_offline_details(products: list) -> None:
    index = _get_offline_detail_index()
    if not index:
        return
    for p in products or []:
        if not isinstance(p, dict):
            continue
        code = (p.get("short_code") or p.get("id") or "").strip().upper()
        if not code:
            continue
        detail = index.get(code)
        if not isinstance(detail, dict):
            continue
        price_min = p.get("price_min", None)
        try:
            price_min_val = float(price_min) if price_min not in (None, "") else 0.0
        except Exception:
            price_min_val = 0.0
        if price_min_val <= 0:
            p["price_min"] = detail.get("price_min", 0.0)
        price_max = p.get("price_max", None)
        try:
            price_max_val = float(price_max) if price_max not in (None, "") else 0.0
        except Exception:
            price_max_val = 0.0
        if price_max_val <= 0:
            p["price_max"] = detail.get("price_max", p.get("price_min", 0.0))
        if not p.get("partner_prices") and isinstance(detail.get("partner_prices"), dict):
            p["partner_prices"] = detail.get("partner_prices")
        if not p.get("partner_price_max") and isinstance(detail.get("partner_price_max"), dict):
            p["partner_price_max"] = detail.get("partner_price_max")
        if not p.get("partner_best_variant") and isinstance(detail.get("partner_best_variant"), dict):
            p["partner_best_variant"] = detail.get("partner_best_variant")
        if (not p.get("partners")) and isinstance(detail.get("partners"), list):
            p["partners"] = detail.get("partners")


def _enrich_product_with_partner_summary(product: dict) -> dict:
    if not isinstance(product, dict) or not product:
        return product

    _enrich_candidates_with_offline_details([product])
    short_code = str(product.get("short_code") or product.get("id") or "").strip().upper()
    if not short_code:
        return product

    variations = _data_agent.fetch_filtered_variations(short_code)
    if not variations:
        return product

    summary_by_partner: Dict[str, Dict[str, Any]] = {}
    for item in variations:
        if not isinstance(item, dict):
            continue
        partner_name = str(item.get("partner_name") or item.get("partner") or "").strip()
        if not partner_name:
            continue
        row = summary_by_partner.setdefault(partner_name, {
            "partner": partner_name,
            "colors": set(),
            "sizes": set(),
            "markets": set(),
            "price_min": None,
            "price_max": None,
        })
        color = str(item.get("color") or "").strip()
        size = str(item.get("size") or "").strip()
        market = str(item.get("location") or product.get("location") or "").strip()
        if color:
            row["colors"].add(color)
        if size:
            row["sizes"].add(size)
        if market:
            row["markets"].add(market)
        try:
            price = float(item.get("price")) if item.get("price") not in (None, "") else None
        except Exception:
            price = None
        if price is not None:
            row["price_min"] = price if row["price_min"] is None else min(row["price_min"], price)
            row["price_max"] = price if row["price_max"] is None else max(row["price_max"], price)

    partner_summary = []
    for partner_name, row in sorted(summary_by_partner.items()):
        partner_summary.append({
            "partner": partner_name,
            "color_count": len(row["colors"]),
            "size_count": len(row["sizes"]),
            "markets": sorted(row["markets"]),
            "price_min": float(row["price_min"]) if row["price_min"] is not None else 0.0,
            "price_max": float(row["price_max"]) if row["price_max"] is not None else float(row["price_min"] or 0.0),
        })

    if partner_summary:
        product["partner_summary"] = sorted(
            partner_summary,
            key=lambda row: (-int(row.get("color_count", 0) or 0), float(row.get("price_min", 0.0) or 0.0), str(row.get("partner", ""))),
        )
    return product


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
    applied_filters: List[dict] = []

    q = (state.get("query") or "").lower()
    pricing_context = state.get("pricing_context", {}) or {}

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

    def _requested_categories() -> set[str]:
        text_parts = [q]
        text_parts.extend((pn or "").lower() for pn in (criteria.get("product_names") or []))
        merged = " ".join(x for x in text_parts if x)
        category_map = {
            "hoodie": ["hoodie", "hooded", "pullover"],
            "sweatshirt": ["sweatshirt", "crewneck"],
            "tshirt": ["áo thun", "ao thun", "t-shirt", "tshirt", "tee"],
            "tanktop": ["tank top", "tanktop", "sleeveless"],
            "longsleeve": ["long sleeve", "longsleeve"],
            "mug": ["mug", "cup"],
            "tote": ["tote", "bag"],
            "poster": ["poster", "canvas"],
        }
        requested = set()
        for category, tokens in category_map.items():
            if any(token in merged for token in tokens):
                requested.add(category)
        return requested

    # Filter theo location
    loc_pref = _infer_location_pref().strip().upper()
    if loc_pref:
        loc_filtered = [
            p for p in filtered
            if _loc_match(p.get("location", ""), loc_pref)
        ]
        filtered = loc_filtered
        applied_filters.append({"type": "location", "value": loc_pref, "mode": "hard"})
        logger.info(f"[Filter] location={loc_pref}: {original_count} → {len(filtered)}")

    if _is_tshirt_query():
        include_terms = ["t-shirt", "tshirt", "tee"]
        exclude_terms = ["kid", "kids", "youth", "baby", "toddler", "infant", "hoodie", "sweatshirt", "crewneck", "tank", "long sleeve", "raglan", "polo", "mug", "poster", "tote", "bag", "cap", "hat", "beanie", "jogger", "pant", "short"]
        tshirt_filtered = []
        for p in filtered:
            name = (p.get("name") or "").lower()
            if not name:
                continue
            if any(t in name for t in exclude_terms):
                continue
            if any(t in name for t in include_terms):
                tshirt_filtered.append(p)
        filtered = tshirt_filtered
        applied_filters.append({"type": "category_hint", "value": "tshirt", "mode": "hard"})
        logger.info(f"[Filter] type=tshirt: → {len(filtered)}")

    requested_categories = _requested_categories()
    if requested_categories:
        category_filtered = [
            p for p in filtered
            if infer_category(p) in requested_categories
        ]
        filtered = category_filtered
        applied_filters.append({"type": "categories", "value": sorted(requested_categories), "mode": "hard"})
        logger.info(f"[Filter] categories={sorted(requested_categories)}: → {len(filtered)}")

    product_names = [x for x in (criteria.get("product_names") or []) if x]
    if product_names and len(product_names) == 1 and any(x in q for x in ["phân tích", "phan tich", "chi tiết", "chi tiet", "kỹ hơn", "ky hon"]):
        token = (product_names[0] or "").strip().lower()
        if token:
            specific = [
                p for p in filtered
                if token in (p.get("name", "") or "").lower()
                or token in (p.get("short_code", "") or "").lower()
            ]
            filtered = specific
            applied_filters.append({"type": "product_name", "value": product_names[0], "mode": "hard"})
            logger.info(f"[Filter] product_name={product_names[0]}: → {len(filtered)}")

    max_price = criteria.get("max_price", 9999.0) or 9999.0
    min_price = criteria.get("min_price", 0.0) or 0.0
    base_cost_max = criteria.get("base_cost_max", 9999.0) or 9999.0
    base_cost_min = criteria.get("base_cost_min", 0.0) or 0.0
    selling_price_max = criteria.get("selling_price_max", 9999.0) or 9999.0
    selling_price_min = criteria.get("selling_price_min", 0.0) or 0.0
    target_margin_min = criteria.get("target_margin_min", 0.0) or 0.0
    target_roi_min = criteria.get("target_roi_min", 0.0) or 0.0
    cost_query = any(token in q for token in ["giá vốn", "gia von", "chi phí", "chi phi", "base cost", "cost"])
    selling_query = any(token in q for token in ["giá bán", "gia ban", "selling price", "sell at", "bán ở", "ban o"])
    if cost_query and base_cost_max >= 9999.0 and max_price < 9999.0:
        base_cost_max = float(max_price)
    if cost_query and base_cost_min <= 0.0 and min_price > 0.0:
        base_cost_min = float(min_price)
    if selling_query and selling_price_max >= 9999.0 and max_price < 9999.0:
        selling_price_max = float(max_price)
    if selling_query and selling_price_min <= 0.0 and min_price > 0.0:
        selling_price_min = float(min_price)
    if not cost_query and not selling_query and base_cost_max >= 9999.0 and max_price < 9999.0:
        base_cost_max = float(max_price)
    if not cost_query and not selling_query and base_cost_min <= 0.0 and min_price > 0.0:
        base_cost_min = float(min_price)
    needs_detail = (
        (max_price < 9999.0)
        or (min_price > 0.0)
        or (base_cost_max < 9999.0)
        or (base_cost_min > 0.0)
        or ("xưởng" in q)
        or ("factory" in q)
        or ("partner" in q)
    )
    if needs_detail:
        _enrich_candidates_with_offline_details(filtered)

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
        filtered = partner_filtered
        applied_filters.append({"type": "partner", "value": partner_prefs, "mode": "hard"})
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
        filtered = color_filtered
        applied_filters.append({"type": "color", "value": color_prefs, "mode": "hard"})
        logger.info(f"[Filter] colors={color_prefs}: → {len(filtered)}")

    # Filter theo giá vốn / base cost
    if base_cost_max < 9999.0:
        price_filtered = []
        for p in filtered:
            raw = p.get("base_cost", None)
            if raw in (None, "", 0, 0.0):
                raw = p.get("price_min", None)
            try:
                val = float(raw)
            except Exception:
                val = None
            if val is None or val <= 0:
                continue
            if val <= float(base_cost_max):
                price_filtered.append(p)
        filtered = price_filtered
        applied_filters.append({"type": "base_cost_max", "value": float(base_cost_max), "mode": "hard"})
        logger.info(f"[Filter] base_cost_max=${base_cost_max}: → {len(filtered)}")

    if base_cost_min > 0.0:
        price_filtered = []
        for p in filtered:
            raw = p.get("base_cost", None)
            if raw in (None, "", 0, 0.0):
                raw = p.get("price_min", None)
            try:
                val = float(raw)
            except Exception:
                val = None
            if val is None or val <= 0:
                continue
            if val >= float(base_cost_min):
                price_filtered.append(p)
        filtered = price_filtered
        applied_filters.append({"type": "base_cost_min", "value": float(base_cost_min), "mode": "hard"})

    # Filter theo giá bán đề xuất
    if selling_price_max < 9999.0:
        price_filtered = []
        for p in filtered:
            code = canonicalize_short_code(p.get("short_code") or p.get("id"))
            pricing = pricing_context.get(code, {}) if code else {}
            raw = pricing.get("selling_price", p.get("suggested_selling_price", None))
            try:
                val = float(raw)
            except Exception:
                val = None
            if val is None or val <= 0:
                continue
            if val <= float(selling_price_max):
                price_filtered.append(p)
        filtered = price_filtered
        applied_filters.append({"type": "selling_price_max", "value": float(selling_price_max), "mode": "hard"})

    if selling_price_min > 0.0:
        price_filtered = []
        for p in filtered:
            code = canonicalize_short_code(p.get("short_code") or p.get("id"))
            pricing = pricing_context.get(code, {}) if code else {}
            raw = pricing.get("selling_price", p.get("suggested_selling_price", None))
            try:
                val = float(raw)
            except Exception:
                val = None
            if val is None or val <= 0:
                continue
            if val >= float(selling_price_min):
                price_filtered.append(p)
        filtered = price_filtered
        applied_filters.append({"type": "selling_price_min", "value": float(selling_price_min), "mode": "hard"})

    if target_margin_min > 0.0:
        margin_filtered = []
        for p in filtered:
            code = canonicalize_short_code(p.get("short_code") or p.get("id"))
            pricing = pricing_context.get(code, {}) if code else {}
            try:
                margin = float(pricing.get("margin", p.get("margin", 0.0)) or 0.0)
            except Exception:
                margin = 0.0
            if margin >= float(target_margin_min):
                margin_filtered.append(p)
        filtered = margin_filtered
        applied_filters.append({"type": "margin_min", "value": float(target_margin_min), "mode": "hard"})

    if target_roi_min > 0.0:
        roi_filtered = []
        for p in filtered:
            code = canonicalize_short_code(p.get("short_code") or p.get("id"))
            pricing = pricing_context.get(code, {}) if code else {}
            try:
                roi = float(pricing.get("roi", p.get("roi", 0.0)) or 0.0)
            except Exception:
                roi = 0.0
            if roi >= float(target_roi_min):
                roi_filtered.append(p)
        filtered = roi_filtered
        applied_filters.append({"type": "roi_min", "value": float(target_roi_min), "mode": "hard"})

    # Filter theo print_method
    print_pref = (criteria.get("print_method") or criteria.get("print_tech") or "").strip().upper()
    if print_pref:
        pm_filtered = [
            p for p in filtered
            if print_pref in (p.get("print_method") or "").upper()
        ]
        filtered = pm_filtered
        applied_filters.append({"type": "print_method", "value": print_pref, "mode": "hard"})
        logger.info(f"[Filter] print_method={print_pref}: → {len(filtered)}")

    # Filter theo max_lead_time
    max_lead = criteria.get("max_lead_time", 999) or 999
    if max_lead < 999:
        lead_filtered = [
            p for p in filtered
            if (
                (p.get("processing_max") or p.get("processing_min") or 999) <= max_lead
            )
        ]
        filtered = lead_filtered
        applied_filters.append({"type": "max_lead_time", "value": int(max_lead), "mode": "hard"})
        logger.info(f"[Filter] max_lead_time={max_lead}: → {len(filtered)}")

    logger.info(f"[Filter] Total: {original_count} → {len(filtered)} candidates after criteria filter")

    return {
        **state,
        "candidates": filtered,
        "products_norm": filtered,
        "applied_filters": applied_filters,
    }


def _loc_match(product_loc: str, pref: str) -> bool:
    loc = (product_loc or "").upper()
    if pref == "US":
        return ("US" in loc) or ("UNITED STATES" in loc)
    if pref == "EU":
        return any(x in loc for x in ("EU", "EUROPE", "POLAND", "GERMANY", "NETHERLANDS", "UK"))
    if pref == "CHINA":
        return "CHINA" in loc
    if pref == "VIETNAM" or pref == "VN":
        return ("VIETNAM" in loc) or (loc == "VN")
    return loc == pref


def _build_data_snapshot_for_validation(state: AgentState) -> dict:
    scores = state.get("scores", []) or []
    top_products = []
    for item in scores[:3]:
        product = item.get("product") if isinstance(item, dict) else None
        if isinstance(product, dict):
            top_products.append(_product_brief(product))

    compare_products = [
        _product_brief(product)
        for product in (state.get("compare_products", []) or [])[:4]
        if isinstance(product, dict)
    ]

    target = _find_target_product(state)
    return {
        "route": state.get("zorin_route", ""),
        "missing_fields": state.get("missing_fields", []) or [],
        "winner": _product_brief(state.get("winner") or {}) if isinstance(state.get("winner"), dict) else {},
        "top_products": top_products,
        "compare_products": compare_products,
        "target_product": _product_brief(target) if target else {},
        "inventory_count": len(state.get("out_of_stock_ids", []) or []),
    }


# ---------------------------------------------------------------------------
# Output node
# ---------------------------------------------------------------------------

def output_node(state: AgentState) -> AgentState:
    query = state.get("query", "") or ""
    # Nếu đã có response_msg (từ zorinask, catalog_info, order) → không generate lại
    if state.get("response_msg") and state.get("zorin_route") == "zorinask":
        return {**state, "response_msg": _localize_response_for_query(query, state.get("response_msg", ""))}
    if state.get("task") == "create_order" and state.get("response_msg"):
        return {**state, "response_msg": _localize_response_for_query(query, state.get("response_msg", ""))}
    if state.get("task") in {"catalog_info", "product_detail_info", "product_partner_info", "other"} and state.get("response_msg"):
        return {**state, "response_msg": _localize_response_for_query(query, state.get("response_msg", ""))}
    state = validate_output_node(state)
    state = generate_response_node(state)
    if state.get("response_msg"):
        return {**state, "response_msg": _localize_response_for_query(query, state.get("response_msg", ""))}
    return state


def output_validator_node(state: AgentState) -> AgentState:
    query = state.get("query", "")
    intent = state.get("intent", "") or ""
    task = state.get("task", "") or intent
    criteria = state.get("extracted_criteria", {}) or {}
    history = state.get("conversation_history", []) or []
    response_msg = state.get("response_msg", "") or ""
    retry_count = int(state.get("retry_count", 0) or 0)
    max_retry_count = int(state.get("max_retry_count", 3) or 3)
    data_snapshot = _build_data_snapshot_for_validation(state)

    decision = _get_flow_validator().validate_output(
        query=query,
        intent=intent,
        task=task,
        criteria=criteria,
        response_msg=response_msg,
        history=history,
        data_snapshot=data_snapshot,
    )
    validator_reason = decision.get("reason", "")
    validator_missing_information = decision.get("missing_information", [])
    reports = _append_validation_report(
        state,
        phase="output",
        passed=bool(decision.get("is_valid", True)),
        task=task,
        reason=validator_reason,
        missing_information=validator_missing_information,
    )

    if decision.get("is_valid", True):
        return {
            **state,
            "validation_reports": reports,
            "validator_reason": "",
            "validator_missing_information": [],
            "validator_next": "memory",
        }

    next_retry = retry_count + 1
    if next_retry > max_retry_count:
        clarification = _build_validator_clarification_message(
            query=query,
            reports=reports,
            missing_information=validator_missing_information,
        )
        return {
            **state,
            "retry_count": next_retry,
            "validation_reports": reports,
            "validator_reason": validator_reason,
            "validator_missing_information": validator_missing_information,
            "response_msg": _localize_response_for_query(query, clarification),
            "validator_next": "memory",
        }

    replanned = _get_flow_validator().replan_task(
        query=query,
        intent=intent,
        current_task=task,
        current_route="output",
        criteria=criteria,
        history=history,
        validation_reason=validator_reason,
        missing_information=validator_missing_information,
        data_snapshot=data_snapshot,
        response_msg=response_msg,
    )
    next_task = (replanned.get("task") or task or intent).strip()
    next_route = (replanned.get("route") or "").strip() or "task_router"
    if next_route not in {"task_router", "memory"}:
        next_route = "task_router"
    reflection_reason = replanned.get("reason", "") or validator_reason
    reflections = _append_reflection_trace(
        state,
        phase="output",
        from_task=task,
        to_task=next_task,
        next_route=next_route,
        validator_reason=validator_reason,
        reflection_reason=reflection_reason,
        missing_information=validator_missing_information,
    )
    logger.info("[OutputValidator] Retry #%s via reflection: %s -> %s", next_retry, task, next_task)
    return {
        **state,
        "retry_count": next_retry,
        "validation_reports": reports,
        "task_replan_reason": reflection_reason,
        "replanned_task": next_task,
        "replanned_route": "",
        "validator_reason": validator_reason,
        "validator_missing_information": validator_missing_information,
        "reflection_trace": reflections,
        "response_msg": "",
        "validator_next": next_route,
    }


def route_after_output_validator(state: AgentState) -> str:
    return state.get("validator_next", "memory")


# ---------------------------------------------------------------------------
# Memory manager node
# ---------------------------------------------------------------------------

def memory_manager_node(state: AgentState) -> AgentState:
    session_id = (state.get("session_id") or "").strip()
    if not session_id:
        return state

    response_msg = state.get("response_msg", "") or ""
    intent = state.get("intent", "") or ""
    returned_objects = _build_returned_objects_payload(state)
    object_snapshot = _build_object_store_snapshot(state)
    metadata: Dict[str, Any] = {
        "scores": state.get("scores", [])[:5],
        "reasons": state.get("reasons", []),
        "winner": state.get("winner") or {},
        "alternatives": state.get("alternatives", [])[:3],
        "returned_objects": returned_objects[:20],
        "applied_filters": state.get("applied_filters", []) or [],
        "validation_errors": state.get("validation_errors", []),
        "validation_reports": state.get("validation_reports", [])[-6:],
        "reflection_trace": state.get("reflection_trace", [])[-6:],
        "task_replan_reason": state.get("task_replan_reason", ""),
        "validator_reason": state.get("validator_reason", ""),
        "validator_missing_information": state.get("validator_missing_information", []) or [],
        "retry_count": state.get("retry_count", 0),
    }
    _object_store.save_snapshot(session_id=session_id, snapshot=object_snapshot)
    _memory.save_message(
        session_id=session_id,
        role="assistant",
        content=response_msg,
        intent=intent,
        metadata=metadata,
    )
    return {
        **state,
        "returned_objects": returned_objects,
        "object_store_snapshot": object_snapshot,
    }
