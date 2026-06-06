"""
LangGraph StateGraph definition & compile
BurgerPrintsAgent - AI Fulfillment Advisor
With execution tracing for graph visualization.
"""
import time
import logging
from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.graph.nodes import (
    detect_intent_node,
    fetch_catalog_node,
    fetch_product_detail_node,
    check_stock_node,
    process_catalog_node,
    market_analysis_node,
    inventory_analysis_node,
    season_weather_node,
    demand_analysis_node,
    pricing_profit_node,
    persona_compatibility_node,
    decision_engine_node,
    compare_node,
    suggest_alternatives_node,
    validate_output_node,
    order_builder_node,
    generate_response_node,
)
from agent.graph.router import route_by_intent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node metadata for graph visualization
# ---------------------------------------------------------------------------

NODE_META = {
    "intent": {
        "label": "🧠 Detect Intent",
        "desc": "Phân tích ý định người dùng",
        "uses_llm": True,
    },
    "fetch": {
        "label": "📦 Fetch Catalog",
        "desc": "Gọi BurgerPrints API lấy danh sách sản phẩm",
        "uses_llm": False,
    },
    "process": {
        "label": "⚙️ Process Catalog",
        "desc": "Parse HTML & normalize dữ liệu sản phẩm",
        "uses_llm": False,
    },
    "market": {
        "label": "🌎 Market Agent",
        "desc": "Phân tích thị trường mục tiêu",
        "uses_llm": False,
    },
    "inventory": {
        "label": "📦 Inventory Agent",
        "desc": "Xác thực tồn kho từ API",
        "uses_llm": False,
    },
    "season_weather": {
        "label": "☀️ Season/Weather",
        "desc": "Tính mùa và khí hậu phù hợp",
        "uses_llm": False,
    },
    "demand": {
        "label": "📈 Demand Signals",
        "desc": "Trend, competition, review proxy",
        "uses_llm": False,
    },
    "pricing_profit": {
        "label": "💰 Pricing/Profit",
        "desc": "Tính giá bán, margin, ROI",
        "uses_llm": False,
    },
    "persona_compat": {
        "label": "🎯 Persona/Compat",
        "desc": "Chấm persona và design-product fit",
        "uses_llm": False,
    },
    "score": {
        "label": "📊 Decision Engine",
        "desc": "Chấm điểm & xếp hạng sản phẩm theo tiêu chí",
        "uses_llm": False,
    },
    "fetch_detail": {
        "label": "🔍 Fetch Detail",
        "desc": "Lấy chi tiết sản phẩm cần so sánh",
        "uses_llm": False,
    },
    "compare": {
        "label": "⚖️ Compare",
        "desc": "So sánh sản phẩm theo tiêu chí",
        "uses_llm": False,
    },
    "stock": {
        "label": "📦 Check Stock",
        "desc": "Kiểm tra sản phẩm hết hàng",
        "uses_llm": False,
    },
    "fetch_for_stock": {
        "label": "📦 Fetch (Stock)",
        "desc": "Lấy catalog cho nhánh kiểm tra tồn kho",
        "uses_llm": False,
    },
    "process_for_stock": {
        "label": "⚙️ Process (Stock)",
        "desc": "Normalize catalog cho nhánh tồn kho",
        "uses_llm": False,
    },
    "alternatives": {
        "label": "🔄 Alternatives",
        "desc": "Đề xuất sản phẩm thay thế",
        "uses_llm": False,
    },
    "validate": {
        "label": "🛡️ Validate Output",
        "desc": "Xác thực sản phẩm/SKU trước khi trả response",
        "uses_llm": False,
    },
    "order_builder": {
        "label": "📝 Order Builder",
        "desc": "Xây dựng payload đơn hàng",
        "uses_llm": False,
    },
    "respond": {
        "label": "💬 Generate Response",
        "desc": "Tạo câu trả lời cuối cùng",
        "uses_llm": False,
    },
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

            # Determine method (AI vs fallback)
            if node_id == "intent":
                # Check if LLM was used or rule-based fallback
                # If error field was cleared (empty string) AND criteria has "summary",
                # rule-based sets error="" explicitly
                criteria = result.get("extracted_criteria", {})
                if criteria.get("summary") and not result.get("error"):
                    # Could be either - check logs
                    method = "ai"  # default; overridden below
                else:
                    method = "ai"

                # Simpler detection: if error was cleared to "" by rule-based
                # The rule-based fallback always populates criteria fully
                rb_keys = {"intent", "location_preference", "max_lead_time", "market",
                           "print_method", "product_names", "budget_concern", "summary"}
                if rb_keys.issubset(set(criteria.keys())):
                    method = "rule-based"
                else:
                    method = "ai"

                intent = result.get("intent", "?")
                loc = criteria.get("location_preference", "")
                summary = f"intent={intent}" + (f", loc={loc}" if loc else "")

            elif node_id in ("fetch", "fetch_for_stock"):
                count = len(result.get("products_raw", []))
                summary = f"{count} products fetched"
                method = "api"

            elif node_id in ("process", "process_for_stock"):
                count = len(result.get("products_norm", []))
                summary = f"{count} products normalized"
                method = "parser"

            elif node_id == "market":
                market = result.get("market_context", {}).get("market", "?")
                summary = f"market={market}"
                method = "algorithm"

            elif node_id == "inventory":
                count = len(result.get("candidates", []))
                oos = len(result.get("out_of_stock_ids", []))
                summary = f"{count} candidates, {oos} out of stock"
                method = "api"

            elif node_id == "season_weather":
                season = result.get("season_context", {}).get("season", "?")
                temp = result.get("weather_context", {}).get("avg_temp", "?")
                summary = f"{season}, avg_temp={temp}"
                method = "algorithm"

            elif node_id == "demand":
                count = len(result.get("demand_signals", {}))
                summary = f"{count} products analyzed"
                method = "algorithm"

            elif node_id == "pricing_profit":
                count = len(result.get("pricing_context", {}))
                summary = f"{count} products priced"
                method = "algorithm"

            elif node_id == "persona_compat":
                count = len(result.get("persona_context", {}))
                summary = f"{count} persona fits"
                method = "algorithm"

            elif node_id == "score":
                scores = result.get("scores", [])
                winner = result.get("winner", {})
                w_name = winner.get("name", "?")[:30] if winner else "none"
                summary = f"top={w_name}, {len(scores)} scored"
                method = "algorithm"

            elif node_id == "fetch_detail":
                count = len(result.get("compare_products", []))
                summary = f"{count} products for comparison"
                method = "api"

            elif node_id == "compare":
                count = len(result.get("candidates", []))
                summary = f"{count} products compared"
                method = "algorithm"

            elif node_id == "stock":
                count = len(result.get("out_of_stock_ids", []))
                summary = f"{count} out of stock"
                method = "api"

            elif node_id == "alternatives":
                count = len(result.get("alternatives", []))
                summary = f"{count} alternatives found"
                method = "algorithm"

            elif node_id == "validate":
                count = len(result.get("validation_errors", []))
                summary = f"{count} validation issues"
                method = "validator"

            elif node_id == "order_builder":
                has_payload = bool(result.get("order_payload"))
                summary = "payload built" if has_payload else "info requested"
                method = "algorithm" if not result.get("error") else "fallback"

            elif node_id == "respond":
                msg = result.get("response_msg", "")
                method = "algorithm" if not result.get("error") else "fallback"
                summary = f"{len(msg)} chars response"

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
            if node_id == "intent":
                criteria = result.get("extracted_criteria", {})
                output = {
                    "intent": result.get("intent", ""),
                    "criteria": criteria,
                }
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
    workflow.add_node("intent", _make_traced_node("intent", detect_intent_node))

    # --- Recommend product branch ---
    workflow.add_node("fetch", _make_traced_node("fetch", fetch_catalog_node))
    workflow.add_node("process", _make_traced_node("process", process_catalog_node))
    workflow.add_node("market", _make_traced_node("market", market_analysis_node))
    workflow.add_node("inventory", _make_traced_node("inventory", inventory_analysis_node))
    workflow.add_node("season_weather", _make_traced_node("season_weather", season_weather_node))
    workflow.add_node("demand", _make_traced_node("demand", demand_analysis_node))
    workflow.add_node("pricing_profit", _make_traced_node("pricing_profit", pricing_profit_node))
    workflow.add_node("persona_compat", _make_traced_node("persona_compat", persona_compatibility_node))
    workflow.add_node("score", _make_traced_node("score", decision_engine_node))

    # --- Compare product branch ---
    workflow.add_node("fetch_detail", _make_traced_node("fetch_detail", fetch_product_detail_node))
    workflow.add_node("compare", _make_traced_node("compare", compare_node))

    # --- Check stock branch ---
    workflow.add_node("stock", _make_traced_node("stock", check_stock_node))
    workflow.add_node("fetch_for_stock", _make_traced_node("fetch_for_stock", fetch_catalog_node))
    workflow.add_node("process_for_stock", _make_traced_node("process_for_stock", process_catalog_node))
    workflow.add_node("alternatives", _make_traced_node("alternatives", suggest_alternatives_node))

    # --- Validation gate ---
    workflow.add_node("validate", _make_traced_node("validate", validate_output_node))

    # --- Order branch ---
    workflow.add_node("order_builder", _make_traced_node("order_builder", order_builder_node))

    # --- Final response ---
    workflow.add_node("respond", _make_traced_node("respond", generate_response_node))

    # ----------------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------------
    workflow.set_entry_point("intent")

    # ----------------------------------------------------------------
    # Conditional routing từ intent node
    # ----------------------------------------------------------------
    workflow.add_conditional_edges(
        "intent",
        route_by_intent,
        {
            "fetch": "fetch",
            "fetch_detail": "fetch_detail",
            "stock": "stock",
            "order_builder": "order_builder",
        },
    )

    # Recommend product flow: fetch -> process -> commerce analysis -> score -> respond
    workflow.add_edge("fetch", "process")
    workflow.add_edge("process", "market")
    workflow.add_edge("market", "inventory")
    workflow.add_edge("inventory", "season_weather")
    workflow.add_edge("season_weather", "demand")
    workflow.add_edge("demand", "pricing_profit")
    workflow.add_edge("pricing_profit", "persona_compat")
    workflow.add_edge("persona_compat", "score")
    workflow.add_edge("score", "validate")

    # Compare product flow: fetch_detail -> compare -> commerce analysis -> score -> respond
    workflow.add_edge("fetch_detail", "compare")
    workflow.add_edge("compare", "market")

    # Check stock flow: stock → fetch_for_stock → process_for_stock → alternatives → respond
    workflow.add_edge("stock", "fetch_for_stock")
    workflow.add_edge("fetch_for_stock", "process_for_stock")
    workflow.add_edge("process_for_stock", "alternatives")
    workflow.add_edge("alternatives", "validate")

    # Order flow: order_builder → respond
    workflow.add_edge("order_builder", "validate")

    # Validation gate to final response
    workflow.add_edge("validate", "respond")

    # Kết thúc
    workflow.add_edge("respond", END)

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
        {"id": "start", "type": "start", "label": "🚀 Start", "x": 400, "y": 0},
        {"id": "intent", "type": "llm", "label": "🧠 Detect Intent", "x": 400, "y": 100},
        # Recommend branch
        {"id": "fetch", "type": "api", "label": "📦 Catalog", "x": 80, "y": 230},
        {"id": "process", "type": "parser", "label": "⚙️ Normalize", "x": 80, "y": 340},
        {"id": "market", "type": "algo", "label": "🌎 Market", "x": 250, "y": 340},
        {"id": "inventory", "type": "api", "label": "📦 Inventory", "x": 420, "y": 340},
        {"id": "season_weather", "type": "algo", "label": "☀️ Season/Weather", "x": 590, "y": 340},
        {"id": "demand", "type": "algo", "label": "📈 Demand", "x": 250, "y": 455},
        {"id": "pricing_profit", "type": "algo", "label": "💰 Pricing/Profit", "x": 420, "y": 455},
        {"id": "persona_compat", "type": "algo", "label": "🎯 Persona/Compat", "x": 590, "y": 455},
        {"id": "score", "type": "algo", "label": "📊 Decision Engine", "x": 420, "y": 570},
        {"id": "validate", "type": "algo", "label": "🛡️ Validate", "x": 420, "y": 680},
        # Compare branch
        {"id": "fetch_detail", "type": "api", "label": "🔍 Fetch Detail", "x": 250, "y": 230},
        {"id": "compare", "type": "algo", "label": "⚖️ Compare", "x": 250, "y": 285},
        # Stock branch
        {"id": "stock", "type": "api", "label": "📦 Check Stock", "x": 760, "y": 230},
        {"id": "fetch_for_stock", "type": "api", "label": "📦 Fetch (Stock)", "x": 760, "y": 340},
        {"id": "process_for_stock", "type": "parser", "label": "⚙️ Process (Stock)", "x": 760, "y": 450},
        {"id": "alternatives", "type": "algo", "label": "🔄 Alternatives", "x": 760, "y": 560},
        # Order branch
        {"id": "order_builder", "type": "algo", "label": "📝 Order Builder", "x": 930, "y": 230},
        # Final
        {"id": "respond", "type": "algo", "label": "💬 Response", "x": 420, "y": 790},
        {"id": "end", "type": "end", "label": "✅ End", "x": 420, "y": 900},
    ],
    "edges": [
        {"source": "start", "target": "intent", "label": ""},
        # Conditional from intent
        {"source": "intent", "target": "fetch", "label": "recommend", "animated": True},
        {"source": "intent", "target": "fetch_detail", "label": "compare", "animated": True},
        {"source": "intent", "target": "stock", "label": "stock", "animated": True},
        {"source": "intent", "target": "order_builder", "label": "order", "animated": True},
        # Recommend flow
        {"source": "fetch", "target": "process", "label": ""},
        {"source": "process", "target": "market", "label": ""},
        {"source": "market", "target": "inventory", "label": ""},
        {"source": "inventory", "target": "season_weather", "label": ""},
        {"source": "season_weather", "target": "demand", "label": ""},
        {"source": "demand", "target": "pricing_profit", "label": ""},
        {"source": "pricing_profit", "target": "persona_compat", "label": ""},
        {"source": "persona_compat", "target": "score", "label": ""},
        {"source": "score", "target": "validate", "label": ""},
        # Compare flow
        {"source": "fetch_detail", "target": "compare", "label": ""},
        {"source": "compare", "target": "market", "label": ""},
        # Stock flow
        {"source": "stock", "target": "fetch_for_stock", "label": ""},
        {"source": "fetch_for_stock", "target": "process_for_stock", "label": ""},
        {"source": "process_for_stock", "target": "alternatives", "label": ""},
        {"source": "alternatives", "target": "validate", "label": ""},
        # Order flow
        {"source": "order_builder", "target": "validate", "label": ""},
        {"source": "validate", "target": "respond", "label": ""},
        # End
        {"source": "respond", "target": "end", "label": ""},
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
    }

    try:
        final_state = graph.invoke(initial_state)
        return {
            "response_msg": final_state.get("response_msg", ""),
            "intent": final_state.get("intent", ""),
            "scores": final_state.get("scores", [])[:5],
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
