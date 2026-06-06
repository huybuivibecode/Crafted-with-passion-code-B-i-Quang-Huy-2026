"""
LangGraph StateGraph definition & compile
BurgerPrintsAgent - AI Fulfillment Advisor
With execution tracing for graph visualization.
"""
import time
import logging
from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.zorin.workflow_nodes import (
    zorin_brain_node,
    intent_analysis_node,
    task_router_node,
    route_after_task_router,
    zorin_ask_node,
    data_agent_node,
    function_node,
    output_node,
    memory_manager_node,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node metadata for graph visualization
# ---------------------------------------------------------------------------

NODE_META = {
    "brain": {"label": "🧠 Zorin Brain", "desc": "Validation + metadata + load/save memory (user msg)", "uses_llm": False},
    "intent_analysis": {"label": "🧩 Intent Analysis", "desc": "Xác định intent & tiêu chí", "uses_llm": True},
    "task_router": {"label": "🧭 Task Router", "desc": "Điều hướng hoặc yêu cầu bổ sung thông tin", "uses_llm": False},
    "zorinask": {"label": "❓ ZorinAsk", "desc": "Thu thập thông tin còn thiếu", "uses_llm": False},
    "data_agent": {"label": "🗃️ Data Agent", "desc": "Lớp truy xuất dữ liệu duy nhất (API/DB) + chuẩn hóa", "uses_llm": False},
    "function": {"label": "🧰 Zorin Function", "desc": "Xử lý nghiệp vụ (recommend/compare/stock/order)", "uses_llm": False},
    "output": {"label": "💬 Output", "desc": "Chuẩn hóa output thân thiện", "uses_llm": False},
    "memory": {"label": "🧠 Memory Manager", "desc": "Ghi memory (assistant msg + metadata)", "uses_llm": False},
}


# ---------------------------------------------------------------------------
# Traced node wrapper
# ---------------------------------------------------------------------------

def _make_traced_node(node_id: str, node_fn):
    """Wrap a node function to add execution tracing."""
    meta = NODE_META.get(node_id, {"label": node_id, "desc": "", "uses_llm": False})

    def traced(state: AgentState) -> AgentState:
        start = time.time()
        error_msg = ""
        method = "unknown"
        summary = ""

        try:
            result = node_fn(state)
            duration_ms = round((time.time() - start) * 1000)

            if node_id == "brain":
                method = "validator"
                summary = f"history={len(result.get('conversation_history', []) or [])}"
            elif node_id == "intent_analysis":
                criteria = result.get("extracted_criteria", {}) or {}
                rb_keys = {
                    "intent",
                    "location_preference",
                    "max_lead_time",
                    "market",
                    "print_method",
                    "product_names",
                    "budget_concern",
                    "partner_preference",
                    "color_preference",
                    "max_price",
                    "min_price",
                    "summary",
                }
                method = "rule-based" if rb_keys.issubset(set(criteria.keys())) else "ai"
                summary = f"intent={result.get('intent', '?')}"
            elif node_id == "task_router":
                summary = f"route={result.get('zorin_route', '?')}, task={result.get('task', '?')}"
                method = "algorithm"
            elif node_id == "zorinask":
                summary = f"missing={len(result.get('missing_fields', []) or [])}"
                method = "fallback"
            elif node_id == "data_agent":
                summary = f"catalog={len(result.get('products_raw', []) or [])}, oos={len(result.get('out_of_stock_ids', []) or [])}"
                method = "api"
            elif node_id == "function":
                task = result.get("task", "") or result.get("intent", "")
                if task == "check_stock":
                    summary = f"alternatives={len(result.get('alternatives', []) or [])}"
                else:
                    scores = result.get("scores", []) or []
                    winner = result.get("winner", {}) or {}
                    summary = f"task={task}, top={(winner.get('short_code') or winner.get('name') or 'none')}"
                    if scores:
                        summary += f", scored={len(scores)}"
                method = "algorithm"
            elif node_id == "output":
                msg = result.get("response_msg", "") or ""
                summary = f"{len(msg)} chars"
                method = "algorithm"
            elif node_id == "memory":
                summary = "assistant saved"
                method = "db"
            else:
                method = "unknown"
                summary = ""

        except Exception as e:
            result = state
            duration_ms = round((time.time() - start) * 1000)
            error_msg = str(e)
            method = "error"
            summary = f"Error: {str(e)[:80]}"

        # ── Build detailed output for node detail view ──
        output = {}
        try:
            if node_id == "brain":
                output = {
                    "session_id": result.get("session_id", ""),
                    "history_count": len(result.get("conversation_history", []) or []),
                    "error": result.get("error", ""),
                }
            elif node_id == "intent_analysis":
                output = {
                    "intent": result.get("intent", ""),
                    "criteria": result.get("extracted_criteria", {}) or {},
                }
            elif node_id == "task_router":
                output = {
                    "route": result.get("zorin_route", ""),
                    "task": result.get("task", ""),
                    "missing_fields": result.get("missing_fields", []) or [],
                }
            elif node_id == "zorinask":
                output = {
                    "missing_fields": result.get("missing_fields", []) or [],
                    "message": result.get("response_msg", ""),
                }
            elif node_id == "data_agent":
                raws = result.get("products_raw", []) or []
                output = {
                    "catalog_count": len(raws),
                    "out_of_stock_count": len(result.get("out_of_stock_ids", []) or []),
                    "compare_count": len(result.get("compare_products", []) or []),
                    "sample": [
                        {"name": p.get("name", "?"), "short_code": p.get("short_code", "")}
                        for p in raws[:10]
                    ],
                }
            elif node_id == "function":
                scores = result.get("scores", []) or []
                output = {
                    "task": result.get("task", "") or result.get("intent", ""),
                    "winner": (result.get("winner") or {}).get("short_code", "") if isinstance(result.get("winner"), dict) else "",
                    "scores_count": len(scores),
                    "alternatives": len(result.get("alternatives", []) or []),
                }
            elif node_id == "output":
                output = {"response": result.get("response_msg", "") or ""}
            elif node_id == "memory":
                output = {"saved": True}
            elif node_id in ("fetch", "fetch_for_stock"):
                raws = result.get("products_raw", [])
                output = {
                    "count": len(raws),
                    "products": [
                        {"name": p.get("name", "?"), "short_code": p.get("short_code", "")}
                        for p in raws[:10]
                    ],
                    "truncated": len(raws) > 10,
                }
            elif node_id in ("process", "process_for_stock"):
                norms = result.get("products_norm", [])
                output = {
                    "count": len(norms),
                    "sample": [
                        {
                            "name": p.get("name", "?"),
                            "location": p.get("location", "?"),
                            "print_method": p.get("print_method", "?"),
                            "processing_time": p.get("processing_time", "?"),
                            "material": p.get("material", "?"),
                        }
                        for p in norms[:8]
                    ],
                }
            elif node_id == "market":
                output = result.get("market_context", {})
            elif node_id == "inventory":
                output = {
                    "candidates": len(result.get("candidates", [])),
                    "out_of_stock": len(result.get("out_of_stock_ids", [])),
                    "snapshot": result.get("inventory_snapshot", {}),
                }
            elif node_id == "season_weather":
                output = {
                    "season": result.get("season_context", {}),
                    "weather": result.get("weather_context", {}),
                }
            elif node_id == "demand":
                signals = result.get("demand_signals", {})
                output = {
                    "count": len(signals),
                    "sample": dict(list(signals.items())[:5]),
                }
            elif node_id == "pricing_profit":
                pricing = result.get("pricing_context", {})
                output = {
                    "count": len(pricing),
                    "sample": dict(list(pricing.items())[:5]),
                }
            elif node_id == "persona_compat":
                persona = result.get("persona_context", {})
                compat = result.get("compatibility_context", {})
                output = {
                    "persona_count": len(persona),
                    "compatibility_count": len(compat),
                    "persona_sample": dict(list(persona.items())[:5]),
                }
            elif node_id == "score":
                scores = result.get("scores", [])
                output = {
                    "total_scored": len(scores),
                    "top_5": [
                        {
                            "rank": i + 1,
                            "name": s.get("product", {}).get("name", "?"),
                            "score": round(s.get("score", 0), 1),
                            "breakdown": s.get("breakdown", {}),
                        }
                        for i, s in enumerate(scores[:5])
                    ],
                    "winner": result.get("winner", {}).get("name", "none"),
                    "reasons": result.get("reasons", []),
                }
            elif node_id == "fetch_detail":
                prods = result.get("compare_products", [])
                output = {
                    "count": len(prods),
                    "products": [
                        {"name": p.get("name", "?"), "short_code": p.get("short_code", "")}
                        for p in prods
                    ],
                }
            elif node_id == "compare":
                cands = result.get("candidates", [])
                output = {
                    "compared": len(cands),
                    "products": [
                        {
                            "name": p.get("name", "?"),
                            "location": p.get("location", "?"),
                            "print_method": p.get("print_method", "?"),
                        }
                        for p in cands
                    ],
                }
            elif node_id == "stock":
                oos = result.get("out_of_stock_ids", [])
                output = {"out_of_stock_ids": oos, "count": len(oos)}
            elif node_id == "alternatives":
                alts = result.get("alternatives", [])
                output = {
                    "count": len(alts),
                    "alternatives": [
                        {"name": p.get("name", "?"), "short_code": p.get("short_code", "")}
                        for p in alts[:5]
                    ],
                }
            elif node_id == "validate":
                output = {
                    "validation_errors": result.get("validation_errors", []),
                    "scores_count": len(result.get("scores", [])),
                    "winner": result.get("winner", {}).get("short_code", "") if isinstance(result.get("winner"), dict) else "",
                }
            elif node_id == "order_builder":
                output = {
                    "payload": result.get("order_payload", {}),
                    "result": result.get("order_result", {}),
                }
            elif node_id == "respond":
                msg = result.get("response_msg", "")
                output = {"response": msg}
        except Exception:
            output = {"error": "Could not extract output"}

        # Append trace entry
        trace = list(result.get("node_trace", []) or [])
        trace.append({
            "node_id": node_id,
            "label": meta["label"],
            "desc": meta["desc"],
            "uses_llm": meta["uses_llm"],
            "method": method,
            "status": "error" if error_msg else "success",
            "duration_ms": duration_ms,
            "summary": summary,
            "error": error_msg,
            "output": output,
        })

        if isinstance(result, dict):
            result["node_trace"] = trace
        return result

    return traced


# ---------------------------------------------------------------------------
# Build & compile graph
# ---------------------------------------------------------------------------

def build_graph():
    """Xây dựng và compile LangGraph StateGraph"""
    workflow = StateGraph(AgentState)

    # ----------------------------------------------------------------
    # Đăng ký tất cả nodes (wrapped with tracing)
    # ----------------------------------------------------------------
    workflow.add_node("brain", _make_traced_node("brain", zorin_brain_node))
    workflow.add_node("intent_analysis", _make_traced_node("intent_analysis", intent_analysis_node))
    workflow.add_node("task_router", _make_traced_node("task_router", task_router_node))
    workflow.add_node("zorinask", _make_traced_node("zorinask", zorin_ask_node))
    workflow.add_node("data_agent", _make_traced_node("data_agent", data_agent_node))
    workflow.add_node("function", _make_traced_node("function", function_node))
    workflow.add_node("output", _make_traced_node("output", output_node))
    workflow.add_node("memory", _make_traced_node("memory", memory_manager_node))

    # ----------------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------------
    workflow.set_entry_point("brain")

    # ----------------------------------------------------------------
    workflow.add_edge("brain", "intent_analysis")
    workflow.add_edge("intent_analysis", "task_router")

    workflow.add_conditional_edges(
        "task_router",
        route_after_task_router,
        {
            "zorinask": "zorinask",
            "data_agent": "data_agent",
        },
    )

    workflow.add_edge("zorinask", "output")
    workflow.add_edge("data_agent", "function")
    workflow.add_edge("function", "output")
    workflow.add_edge("output", "memory")
    workflow.add_edge("memory", END)

    return workflow.compile()


# Singleton - compile graph một lần khi khởi động
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ---------------------------------------------------------------------------
# Graph definition for frontend visualization
# ---------------------------------------------------------------------------

GRAPH_DEFINITION = {
    "nodes": [
        {"id": "start", "type": "start", "label": "🚀 Start", "x": 120, "y": 60},
        {"id": "brain", "type": "algo", "label": "🧠 Zorin Brain", "x": 280, "y": 60},
        {"id": "intent_analysis", "type": "llm", "label": "🧩 Intent Analysis", "x": 460, "y": 60},
        {"id": "task_router", "type": "algo", "label": "🧭 Task Router", "x": 650, "y": 60},
        {"id": "zorinask", "type": "algo", "label": "❓ ZorinAsk", "x": 650, "y": 180},
        {"id": "data_agent", "type": "api", "label": "🗃️ Data Agent", "x": 820, "y": 60},
        {"id": "function", "type": "algo", "label": "🧰 Zorin Function", "x": 1000, "y": 60},
        {"id": "output", "type": "algo", "label": "💬 Output", "x": 820, "y": 300},
        {"id": "memory", "type": "algo", "label": "🧠 Memory Manager", "x": 640, "y": 300},
        {"id": "end", "type": "end", "label": "✅ End", "x": 460, "y": 300},
    ],
    "edges": [
        {"source": "start", "target": "brain", "label": ""},
        {"source": "brain", "target": "intent_analysis", "label": ""},
        {"source": "intent_analysis", "target": "task_router", "label": ""},
        {"source": "task_router", "target": "zorinask", "label": "thiếu dữ liệu", "animated": True},
        {"source": "task_router", "target": "data_agent", "label": "đủ dữ liệu", "animated": True},
        {"source": "data_agent", "target": "function", "label": ""},
        {"source": "function", "target": "output", "label": ""},
        {"source": "zorinask", "target": "output", "label": ""},
        {"source": "output", "target": "memory", "label": ""},
        {"source": "memory", "target": "end", "label": ""},
    ],
}


def run_agent(query: str, session_id: str = "", conversation_history: list = None) -> dict:
    """
    Chạy agent với query và trả về kết quả + execution trace.
    """
    graph = get_graph()

    initial_state: AgentState = {
        "query": query,
        "session_id": session_id,
        "conversation_history": conversation_history or [],
        "intent": "",
        "extracted_criteria": {},
        "products_raw": [],
        "products_norm": [],
        "catalog_index": {},
        "candidates": [],
        "scores": [],
        "winner": None,
        "market_context": {},
        "season_context": {},
        "weather_context": {},
        "demand_signals": {},
        "pricing_context": {},
        "persona_context": {},
        "compatibility_context": {},
        "evidence": [],
        "compare_ids": [],
        "compare_products": [],
        "out_of_stock_ids": [],
        "inventory_snapshot": {},
        "alternatives": [],
        "order_payload": {},
        "order_result": {},
        "reasons": [],
        "response_msg": "",
        "error": "",
        "validation_errors": [],
        "node_trace": [],
        "zorin_route": "data_agent",
        "task": "",
        "missing_fields": [],
    }

    try:
        final_state = graph.invoke(initial_state)
        criteria = final_state.get("extracted_criteria") or {}
        return {
            "response_msg": final_state.get("response_msg", ""),
            "intent": final_state.get("intent", ""),
            "extracted_criteria": criteria,
            "scores": final_state.get("scores", []),
            "reasons": final_state.get("reasons", []),
            "winner": final_state.get("winner"),
            "alternatives": final_state.get("alternatives", []),
            "market_context": final_state.get("market_context", {}),
            "season_context": final_state.get("season_context", {}),
            "weather_context": final_state.get("weather_context", {}),
            "evidence": final_state.get("evidence", []),
            "validation_errors": final_state.get("validation_errors", []),
            "error": final_state.get("error", ""),
            "node_trace": final_state.get("node_trace", []),
        }

    except Exception as e:
        return {
            "response_msg": f"❌ Đã xảy ra lỗi xử lý: {str(e)}",
            "intent": "",
            "scores": [],
            "reasons": [],
            "winner": None,
            "alternatives": [],
            "market_context": {},
            "season_context": {},
            "weather_context": {},
            "evidence": [],
            "validation_errors": [],
            "error": str(e),
            "node_trace": [],
        }
