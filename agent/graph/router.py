"""
LangGraph Router - Conditional routing logic sau Intent Node
"""
from agent.graph.state import AgentState


def route_by_intent(state: AgentState) -> str:
    """
    Sau khi detect_intent, chọn nhánh tiếp theo trong graph.
    Returns: tên node tiếp theo
    """
    intent = state.get("intent", "recommend_product")

    routes = {
        "recommend_product": "fetch",
        "compare_product": "fetch_detail",
        "check_stock": "stock",
        "create_order": "order_builder",
        "general_inquiry": "fetch",
    }

    return routes.get(intent, "fetch")
