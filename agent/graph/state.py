"""
AgentState - TypedDict định nghĩa toàn bộ state của LangGraph pipeline
"""
from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    # Input
    query: str                          # Câu hỏi người dùng
    session_id: str                     # ID phiên chat
    conversation_history: List[dict]    # Lịch sử hội thoại [{role, content}]

    # Intent detection
    intent: str                         # recommend_product | compare_product | check_stock | create_order
    extracted_criteria: dict            # Tiêu chí trích xuất: location, max_lead_time, market, print_method...

    # Product data
    products_raw: List[dict]            # Dữ liệu thô từ BurgerPrints API
    products_norm: List[dict]           # Dữ liệu đã normalize + parse html_desc
    catalog_index: dict                 # Canonical product lookup maps
    candidates: List[dict]              # Danh sách ứng viên sau lọc
    scores: List[dict]                  # [{product, score, breakdown}]
    winner: Optional[dict]              # Sản phẩm được chọn

    # Commerce decision context
    market_context: dict                # Market profile and category preferences
    season_context: dict                # Season inferred from market/date
    weather_context: dict               # Weather/climate suitability context
    demand_signals: dict                # Trend, competition, and review proxy scores
    pricing_context: dict               # Pricing, margin, profit, ROI per product
    persona_context: dict               # Persona fit per product
    compatibility_context: dict         # Design/product fit per product
    evidence: List[dict]                # Traceable evidence used by scoring

    # Comparison
    compare_ids: List[str]              # IDs sản phẩm cần so sánh
    compare_products: List[dict]        # Chi tiết các sản phẩm so sánh

    # Out of stock
    out_of_stock_ids: List[str]         # IDs đang hết hàng
    inventory_snapshot: dict            # Trạng thái tồn kho chuẩn hóa
    alternatives: List[dict]            # Sản phẩm thay thế

    # Order creation
    order_payload: dict                 # Payload cho POST /v2/order
    order_result: dict                  # Kết quả từ API

    # Output
    reasons: List[str]                  # Lý do chọn sản phẩm
    response_msg: str                   # Câu trả lời cuối cùng
    error: str                          # Thông báo lỗi (nếu có)
    validation_errors: List[str]        # Lỗi chuẩn hóa/validation đầu ra

    # Execution trace (for graph visualization)
    node_trace: List[dict]              # [{node_id, label, status, method, duration_ms, summary, error}]
