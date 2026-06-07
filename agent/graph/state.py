"""
AgentState - TypedDict dinh nghia toan bo state cua LangGraph pipeline
"""
from typing import List, Optional, TypedDict


class AgentState(TypedDict):
    # Input
    query: str
    session_id: str
    conversation_history: List[dict]

    # Intent detection
    intent: str
    extracted_criteria: dict

    # Product data
    products_raw: List[dict]
    products_norm: List[dict]
    catalog_index: dict
    candidates: List[dict]
    scores: List[dict]
    winner: Optional[dict]

    # Commerce decision context
    market_context: dict
    season_context: dict
    weather_context: dict
    demand_signals: dict
    pricing_context: dict
    persona_context: dict
    compatibility_context: dict
    evidence: List[dict]

    # Comparison
    compare_ids: List[str]
    compare_products: List[dict]

    # Out of stock
    out_of_stock_ids: List[str]
    inventory_snapshot: dict
    alternatives: List[dict]
    returned_objects: List[dict]
    object_store_snapshot: dict
    applied_filters: List[dict]

    # Order creation
    order_payload: dict
    order_result: dict

    # Output
    reasons: List[str]
    response_msg: str
    error: str
    validation_errors: List[str]

    # Execution trace
    node_trace: List[dict]

    # Zorin orchestration
    zorin_route: str
    task: str
    missing_fields: List[str]
    task_replan_reason: str
    replanned_task: str
    replanned_route: str
    validator_reason: str
    validator_missing_information: List[str]
    reflection_trace: List[dict]
    retry_count: int
    max_retry_count: int
    validation_reports: List[dict]
    validator_next: str
