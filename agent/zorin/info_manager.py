"""
Zorin Info Manager - Phân tích intent và routing tasks
Chứa IntentAnalyzer, TaskRouter, ZorinAsk

Intent types mở rộng:
- recommend_product: Tìm / gợi ý sản phẩm
- compare_product: So sánh sản phẩm
- check_stock: Kiểm tra tồn kho
- create_order: Tạo đơn hàng
- catalog_info: Hỏi thông tin catalog (partner nào có?, loại sản phẩm?, giá range?, ...)
- product_detail_info: Hỏi chi tiết của một sản phẩm cụ thể (màu, size, chất liệu, công nghệ in, lead time, ...)
- general_inquiry: Câu hỏi chung về POD, không cần catalog
- other: fallback task dùng LLM khi query cần suy luận mở + data nhưng không khớp trọn với function cứng
"""
import json
import re
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from django.conf import settings
from agent.services.api_knowledge import get_api_knowledge
from agent.zorin.language import detect_response_language

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Knowledge shared across all LLM-backed helpers
# ---------------------------------------------------------------------------
API_KNOWLEDGE = get_api_knowledge()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class IntentCriteria(BaseModel):
    """Schema output từ IntentAnalyzer - mở rộng với catalog_info intent"""
    intent: str = Field(
        description=(
            "One of: recommend_product | compare_product | check_stock | create_order "
            "| catalog_info | product_detail_info | general_inquiry | other. "
            "catalog_info: hỏi về thông tin catalog (partner nào có, loại sản phẩm, giá, màu, location, ...)"
        )
    )
    catalog_query_type: str = Field(
        default="",
        description=(
            "Chỉ dùng khi intent=catalog_info. "
            "One of: partners | product_types | colors | locations | print_methods | price_range | general"
        )
    )
    location_preference: str = Field(default="", description="Market/location: US, EU, China, Vietnam, etc.")
    max_lead_time: int = Field(default=999, description="Max acceptable lead time in business days")
    market: str = Field(default="", description="Target selling market")
    print_method: str = Field(default="", description="Preferred print method: DTG, Sublimation, etc.")
    product_names: List[str] = Field(default_factory=list, description="Specific product names or codes mentioned")
    budget_concern: bool = Field(default=False, description="User mentioned cost/price concern")
    summary: str = Field(default="", description="Brief summary of user intent in Vietnamese")
    partner_preference: List[str] = Field(default_factory=list, description="Preferred partners: Spire, Bella + Canvas, Gildan, etc.")
    color_preference: List[str] = Field(default_factory=list, description="Preferred colors: black, white, blue, red, etc.")
    max_price: float = Field(default=9999.0, description="Maximum price limit")
    min_price: float = Field(default=0.0, description="Minimum price limit")
    base_cost_max: float = Field(default=9999.0, description="Maximum acceptable base cost / cost price")
    base_cost_min: float = Field(default=0.0, description="Minimum acceptable base cost / cost price")
    selling_price_max: float = Field(default=9999.0, description="Maximum acceptable selling price")
    selling_price_min: float = Field(default=0.0, description="Minimum acceptable selling price")
    target_margin_min: float = Field(default=0.0, description="Minimum acceptable margin percentage")
    target_roi_min: float = Field(default=0.0, description="Minimum acceptable ROI percentage")
    skus: List[str] = Field(default_factory=list, description="Extracted SKU codes from product names")
    shipping_location: str = Field(default="", description="Shipping destination location")
    print_tech: str = Field(default="", description="Print technology preference")
    quantity: int = Field(default=0, description="Quantity if mentioned")
    size_preference: str = Field(default="", description="Size preference if mentioned (S, M, L, XL, ...)")
    list_all: bool = Field(
        default=False,
        description=(
            "True khi user muốn xem TOÀN BỘ danh sách sản phẩm, không chỉ top. "
            "Dấu hiệu: 'toàn bộ', 'tất cả', 'danh sách', 'liệt kê', 'cho tôi hết', 'list all', 'all'."
        )
    )


class FollowUpResolution(BaseModel):
    """Schema output cho bước resolve follow-up theo ngữ cảnh hội thoại."""
    should_resolve: bool = Field(
        default=False,
        description="True nếu query hiện tại đang tham chiếu tới sản phẩm đã xuất hiện trong các lượt trước."
    )
    selected_indices: List[int] = Field(
        default_factory=list,
        description="Danh sách chỉ số 1-based của các sản phẩm trong recent_products mà query đang tham chiếu."
    )
    reason: str = Field(
        default="",
        description="Giải thích ngắn gọn bằng tiếng Việt về cách resolve ngữ cảnh."
    )


class ContextTaskRefinement(BaseModel):
    """Schema output cho bước tinh chỉnh task theo product context."""
    should_override: bool = Field(
        default=False,
        description="True nếu cần override task mặc định dựa trên product context vừa resolve."
    )
    task: str = Field(
        default="",
        description="Task override. Hiện hỗ trợ product_partner_info, product_detail_info hoặc để trống."
    )
    reason: str = Field(
        default="",
        description="Giải thích ngắn gọn vì sao cần override task."
    )


class OtherTaskRoutingDecision(BaseModel):
    """Schema quyết định có override sang task other hay không."""
    use_other: bool = Field(
        default=False,
        description="True nếu query nên được xử lý bằng task fallback `other` thay vì function cứng."
    )
    reason: str = Field(
        default="",
        description="Giải thích ngắn gọn bằng tiếng Việt về lý do route sang other hoặc giữ task hiện tại."
    )


class OtherTaskPlan(BaseModel):
    """Schema cho bước lập kế hoạch xử lý của task other."""
    action: str = Field(
        default="answer_with_current_data",
        description=(
            "One of: answer_with_current_data | fetch_variations_then_answer | "
            "fetch_compare_details_then_answer | ask_user"
        )
    )
    answer_goal: str = Field(
        default="",
        description="Mục tiêu trả lời ngắn gọn: phân tích, tư vấn, giải thích, lọc điều kiện, follow-up..."
    )
    target_product_names: List[str] = Field(
        default_factory=list,
        description="Tên sản phẩm nên dùng để fetch dữ liệu bổ sung nếu cần."
    )
    target_skus: List[str] = Field(
        default_factory=list,
        description="SKU nên dùng để fetch dữ liệu bổ sung nếu cần."
    )
    information_needed_from_user: List[str] = Field(
        default_factory=list,
        description="Chỉ liệt kê khi thật sự thiếu thông tin và không thể giải quyết bằng dữ liệu hiện có."
    )
    reason: str = Field(
        default="",
        description="Giải thích vì sao chọn action này."
    )


class OtherTaskResponse(BaseModel):
    """Schema đầu ra cuối của task other."""
    status: str = Field(
        default="answer",
        description="One of: answer | ask_user"
    )
    response: str = Field(
        default="",
        description="Câu trả lời cuối bằng tiếng Việt, chuyên nghiệp, rõ ràng, bám sát dữ liệu."
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Danh sách thông tin còn thiếu nếu status=ask_user."
    )


class FlowValidationDecision(BaseModel):
    """Kết quả đánh giá của validator cho một bước trong luồng."""
    is_valid: bool = Field(
        default=True,
        description="True nếu task/output hiện tại phù hợp với query và scope dữ liệu."
    )
    reason: str = Field(
        default="",
        description="Giải thích ngắn gọn bằng tiếng Việt vì sao pass hoặc fail."
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Danh sách thông tin còn thiếu nếu không thể xử lý chính xác."
    )


class TaskReplanDecision(BaseModel):
    """Quyết định task mới khi task cũ bị validator cấm cho message hiện tại."""
    task: str = Field(
        default="",
        description=(
            "Một task hợp lệ trong các giá trị: recommend_product | compare_product | check_stock | "
            "create_order | catalog_info | product_partner_info | general_inquiry | other"
        )
    )
    route: str = Field(
        default="task_router",
        description="BÆ°á»›c káº¿ tiáº¿p nÃªn Ä‘i tá»›i: task_router | data_agent | zorinask | memory"
    )
    reason: str = Field(
        default="",
        description="Giải thích ngắn gọn vì sao task này là lựa chọn thay thế tốt hơn."
    )


def _extract_first_money_value(query: str, patterns: List[str]) -> float | None:
    text = str(query or "")
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        for group in match.groups():
            if group is None:
                continue
            try:
                return float(str(group).replace(",", "").strip())
            except Exception:
                continue
    return None


def _postprocess_numeric_constraints(query: str, criteria: Dict[str, Any]) -> Dict[str, Any]:
    criteria = dict(criteria or {})
    q = (query or "").lower()

    base_cost_max = _extract_first_money_value(q, [
        r"giá vốn\s*(?:dưới|<|<=|tối đa|khoảng)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"chi phí\s*(?:dưới|<|<=|tối đa|khoảng)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"base cost\s*(?:under|below|<=|less than|max|around)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"cost\s*(?:under|below|<=|less than|max|around)?\s*\$?\s*(\d+(?:\.\d+)?)",
    ])
    if base_cost_max is not None:
        criteria["base_cost_max"] = base_cost_max
    else:
        criteria.setdefault("base_cost_max", 9999.0)

    selling_price_max = _extract_first_money_value(q, [
        r"giá bán\s*(?:dưới|<|<=|tối đa|khoảng)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"bán\s*(?:ở|tầm|khoảng)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"selling price\s*(?:under|below|<=|less than|max|around)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"sell(?:ing)?\s*(?:at|around|under|below)?\s*\$?\s*(\d+(?:\.\d+)?)",
    ])
    if selling_price_max is not None:
        criteria["selling_price_max"] = selling_price_max
    else:
        criteria.setdefault("selling_price_max", 9999.0)

    roi_min = _extract_first_money_value(q, [
        r"roi\s*(?:trên|>|>=|ít nhất|tối thiểu|over|above|at least|min)?\s*(\d+(?:\.\d+)?)\s*%",
    ])
    if roi_min is not None:
        criteria["target_roi_min"] = roi_min
    else:
        criteria.setdefault("target_roi_min", 0.0)

    margin_min = _extract_first_money_value(q, [
        r"margin\s*(?:trên|>|>=|ít nhất|tối thiểu|over|above|at least|min)?\s*(\d+(?:\.\d+)?)\s*%",
        r"biên lợi nhuận\s*(?:trên|>|>=|ít nhất|tối thiểu)?\s*(\d+(?:\.\d+)?)\s*%",
    ])
    if margin_min is not None:
        criteria["target_margin_min"] = margin_min
    else:
        criteria.setdefault("target_margin_min", 0.0)

    if criteria.get("base_cost_max", 9999.0) < 9999.0:
        criteria["budget_concern"] = True

    return criteria


# ---------------------------------------------------------------------------
# Intent Analyzer
# ---------------------------------------------------------------------------

class IntentAnalyzer:
    """Phân tích intent từ user query dùng LLM"""

    @staticmethod
    def analyze(query: str, history: List[Dict] = None) -> Dict[str, Any]:
        """
        Phân tích intent và trích xuất criteria từ query

        Returns:
            Dict với keys: intent, extracted_criteria, error
        """
        try:
            llm = IntentAnalyzer._get_llm()

            # Build context từ history (3 message gần nhất)
            context = ""
            if history:
                context = "\n".join([
                    f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                    for msg in history[-3:]
                ])

            system_prompt = f"""Bạn là Zorin AI Assistant - chuyên gia phân tích intent cho hệ thống POD BurgerPrints.

{API_KNOWLEDGE}

NHIỆM VỤ: Phân tích câu hỏi → xác định intent → trích xuất criteria.

CÁC INTENT VÀ KHI NÀO DÙNG:

1. **recommend_product**: Tìm / gợi ý sản phẩm phù hợp để bán
   - "Tôi muốn bán áo thun cho thị trường Mỹ"
   - "Tìm sản phẩm dưới $12, ship US"
   - "Gợi ý sản phẩm POD tốt nhất"
   - "Seller mới nên bán gì?"

2. **compare_product**: So sánh nhiều sản phẩm cụ thể
   - "So sánh Gildan 5000 với Gildan 64000"
   - "Comfort Colors 1566 vs Bella + Canvas 3001 cái nào tốt hơn?"

3. **check_stock**: Kiểm tra tình trạng tồn kho
   - "Sản phẩm này còn hàng không?"
   - "Bella + Canvas 3001 còn stock không?"
   - "Hết hàng chưa?"

4. **create_order**: Tạo / đặt đơn hàng
   - "Tạo đơn hàng cho tôi"
   - "Đặt 2 cái áo size M, ship về..."
   - "Tôi muốn order SKU USG5000"

5. **catalog_info**: Hỏi thông tin về catalog/danh mục (KHÔNG phải gợi ý sản phẩm cụ thể)
   - "Hiện có những partner nào?" → catalog_query_type: partners
   - "BurgerPrints có những loại sản phẩm gì?" → catalog_query_type: product_types
   - "Có màu sắc nào?" → catalog_query_type: colors
   - "Kho hàng ở đâu?" → catalog_query_type: locations
   - "Phương pháp in nào được hỗ trợ?" → catalog_query_type: print_methods
   - "Giá sản phẩm range bao nhiêu?" → catalog_query_type: price_range
   - "Catalog có bao nhiêu sản phẩm?" → catalog_query_type: general

6. **product_detail_info**: Hỏi chi tiết của MỘT sản phẩm cụ thể
   - "Gildan 5000 có những màu nào?"
   - "Bella + Canvas 3719 có size nào?"
   - "Cho tôi thông tin chi tiết sản phẩm này"
   - "Mẫu này dùng công nghệ in gì, chất liệu gì?"

7. **general_inquiry**: Câu hỏi chung về POD không cần catalog
   - "POD là gì?"
   - "Làm sao để bắt đầu bán POD?"
   - "Phí ship như thế nào?"

8. **other**: Fallback khi query cần suy luận mở có dùng data nhưng không khớp trọn với function cứng
   - "Dựa trên mẫu vừa rồi, phân tích giúp tôi nên đi phân khúc nào"
   - "Nếu ưu tiên tốc độ nhưng vẫn giữ biên lợi nhuận, nên chọn hướng nào?"
   - "Từ các mẫu trước đó, giải thích vì sao mẫu này phù hợp hơn"
   - "Hãy đọc dữ liệu hiện có rồi tư vấn giúp tôi bước tiếp theo"

OUTPUT FORMAT (JSON):
{{
    "intent": "...",
    "catalog_query_type": "partners|product_types|colors|locations|print_methods|price_range|general",
    "location_preference": "US/EU/China/Vietnam/...",
    "max_lead_time": số_ngày,
    "market": "thị_trường_mục_tiêu",
    "print_method": "DTG/Sublimation/...",
    "product_names": ["tên_sp_1", "tên_sp_2"],
    "budget_concern": true/false,
    "summary": "tóm_tắt_bằng_tiếng_Việt",
    "partner_preference": ["Spire", "Bella + Canvas", ...],
    "color_preference": ["black", "white", "blue", ...],
    "max_price": số_tối_đa,
    "min_price": số_tối_thiểu,
    "base_cost_max": giá_vốn_tối_đa,
    "base_cost_min": giá_vốn_tối_thiểu,
    "selling_price_max": giá_bán_tối_đa,
    "selling_price_min": giá_bán_tối_thiểu,
    "target_margin_min": margin_tối_thiểu_theo_%,
    "target_roi_min": ROI_tối_thiểu_theo_%,
    "skus": ["mã_SKU_1"],
    "shipping_location": "địa_chỉ_giao_hàng",
    "print_tech": "công_nghệ_in",
    "quantity": số_lượng_nếu_có,
    "size_preference": "size_nếu_có"
}}

VÍ DỤ:
- "hiện tại đang có những partner nào" → intent: catalog_info, catalog_query_type: partners
- "Tìm áo màu đen, partner Spire, dưới $12 ship US" → intent: recommend_product, partner_preference: ["Spire"], color_preference: ["black"], max_price: 12.0, location_preference: "US"
- "Tôi muốn bán T-shirt cho thị trường Mỹ, giá vốn dưới $8, ship dưới 5 ngày" → intent: recommend_product, location_preference: "US", base_cost_max: 8.0, max_lead_time: 5
- "So sánh Comfort Colors 1566 với Bella + Canvas 3945" → intent: compare_product, product_names: ["Comfort Colors 1566", "Bella + Canvas 3945"]
- "Còn hàng áo hoodie màu xanh không?" → intent: check_stock, product_names: ["hoodie"], color_preference: ["blue"]
- "Unisex T-Shirt Gildan 5000 có những màu nào?" → intent: product_detail_info, product_names: ["Gildan 5000"]

CHÚ Ý:
- Ưu tiên catalog_info khi câu hỏi mang tính liệt kê/thống kê về catalog
- Nếu câu hỏi nhắm tới một sản phẩm cụ thể và hỏi màu, size, chất liệu, công nghệ in, processing time hoặc thông tin chi tiết thì ưu tiên product_detail_info
- Luôn trích xuất tối đa thông tin từ query và history
- Tóm tắt bằng tiếng Việt rõ ràng"""

            user_content = query
            if context:
                user_content = f"Context hội thoại:\n{context}\n\nCâu hỏi hiện tại: {query}"

            llm_structured = llm.with_structured_output(IntentCriteria)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]

            result = llm_structured.invoke(messages)
            criteria = result.model_dump() if hasattr(result, "model_dump") else result.dict()
            criteria = _postprocess_numeric_constraints(query, criteria)

            # Post-process: tự động extract SKUs từ product_names nếu chưa có
            if not criteria.get("skus"):
                criteria["skus"] = extract_skus_from_names(criteria.get("product_names", []))

            q = (query or "").strip()
            q_lower = q.lower()

            m = re.search(r"\b(\d{1,3})\b\s*(?:sản\s*phẩm|sp)\b", q_lower)
            requested_count = int(m.group(1)) if m else 0
            if requested_count > 0:
                criteria["list_all"] = False

            if not (criteria.get("location_preference") or "").strip():
                if any(x in q_lower for x in ["thị trường mỹ", "thi truong my", "mỹ", "my", "us", "usa", "united states"]):
                    criteria["location_preference"] = "US"
                elif any(x in q_lower for x in ["thị trường trung quốc", "thi truong trung quoc", "trung quốc", "trung quoc", "china"]):
                    criteria["location_preference"] = "China"
                elif any(x in q_lower for x in ["thị trường việt nam", "thi truong viet nam", "việt nam", "viet nam", "vietnam", "vn"]):
                    criteria["location_preference"] = "Vietnam"
                elif any(x in q_lower for x in ["thị trường eu", "thi truong eu", "châu âu", "chau au", "europe", "eu"]):
                    criteria["location_preference"] = "EU"

            if result.intent == "compare_product":
                product_names = [x for x in (criteria.get("product_names") or []) if x]
                if len(product_names) == 1:
                    one = product_names[0].lower()
                    for sep in [" vs ", " vs. ", " với ", " so với ", " và ", " compare ", " versus "]:
                        if sep in one:
                            parts = [
                                p.strip()
                                for p in re.split(r"\bvs\.?\b|\bvới\b|\bso với\b|\bvà\b|\bversus\b", product_names[0], flags=re.IGNORECASE)
                                if p.strip()
                            ]
                            if len(parts) >= 2:
                                criteria["product_names"] = parts[:2]
                                break
                if len((criteria.get("product_names") or [])) < 2 and any(x in q_lower for x in [" so sánh ", "so sánh", "compare", " vs ", " với ", " so với ", " versus "]):
                    for sep in [" so sánh ", "compare "]:
                        if q_lower.startswith(sep):
                            q_tail = q[len(sep):].strip()
                            q_lower = q.lower()
                            break
                    else:
                        q_tail = q
                    q_tail_lower = q_tail.lower()
                    for sep in [" với ", " vs ", " vs. ", " so với ", " và ", " versus "]:
                        idx = q_tail_lower.find(sep)
                        if idx >= 0:
                            left = q_tail[:idx].strip()
                            right = q_tail[idx + len(sep):].strip()
                            if left and right:
                                criteria["product_names"] = [left, right]
                            break

            if "phân tích" in q_lower or "phan tich" in q_lower or "chi tiết" in q_lower or "chi tiet" in q_lower:
                if result.intent == "compare_product" and not any(x in q_lower for x in ["so sánh", "compare", "vs"]):
                    result.intent = "recommend_product"

                if not criteria.get("product_names"):
                    m = re.search(r"(?:phân tích|phan tich)(?:\s+chi\s*tiết|\s+chi\s*tiet|\s+kỹ\s+hơn|\s+ky\s+hon)?\s*(.+)$", q_lower)
                    if m:
                        name = (m.group(1) or "").strip()
                        if name:
                            criteria["product_names"] = [name]
                            if not criteria.get("skus"):
                                criteria["skus"] = extract_skus_from_names(criteria.get("product_names", []))

            detail_tokens = [
                "màu", "mau", "size", "kích thước", "kich thuoc", "biến thể", "bien the",
                "chi tiết", "chi tiet", "thông tin", "thong tin", "chất liệu", "chat lieu",
                "công nghệ in", "cong nghe in", "processing time", "lead time", "print method",
            ]
            if (
                (criteria.get("product_names") or criteria.get("skus"))
                and any(token in q_lower for token in detail_tokens)
                and result.intent not in {"compare_product", "create_order", "check_stock"}
            ):
                result.intent = "product_detail_info"

            logger.info(f"IntentAnalyzer: intent={result.intent}, catalog_type={result.catalog_query_type}, summary={result.summary}")

            return {
                "intent": result.intent,
                "extracted_criteria": criteria,
                "error": None
            }

        except Exception as e:
            logger.error(f"IntentAnalyzer failed: {e}")
            # Fallback: rule-based
            return IntentAnalyzer._rule_based_fallback(query)

    @staticmethod
    def _rule_based_fallback(query: str) -> Dict[str, Any]:
        """Rule-based fallback khi LLM lỗi"""
        q = query.lower()
        intent = "general_inquiry"
        catalog_query_type = ""

        # Catalog info patterns
        if any(kw in q for kw in ["partner nào", "những partner", "có partner", "danh sách partner"]):
            intent = "catalog_info"
            catalog_query_type = "partners"
        elif any(kw in q for kw in ["loại sản phẩm", "có những gì", "danh mục", "product gì"]):
            intent = "catalog_info"
            catalog_query_type = "product_types"
        elif any(kw in q for kw in ["màu nào", "có màu gì", "những màu"]):
            intent = "catalog_info"
            catalog_query_type = "colors"
        elif any(kw in q for kw in ["phương pháp in", "print method", "dtg", "sublimation"]):
            intent = "catalog_info"
            catalog_query_type = "print_methods"
        elif any(kw in q for kw in ["giá range", "giá bao nhiêu", "khoảng giá"]):
            intent = "catalog_info"
            catalog_query_type = "price_range"
        elif any(kw in q for kw in ["kho hàng", "warehouse", "location"]):
            intent = "catalog_info"
            catalog_query_type = "locations"
        elif any(kw in q for kw in ["có màu nào", "co mau nao", "màu gì", "mau gi", "size nào", "size gi", "chi tiết sản phẩm", "chi tiet san pham", "thông tin sản phẩm", "thong tin san pham"]):
            intent = "product_detail_info"
        # Other intents
        elif any(kw in q for kw in ["so sánh", "compare", "vs", "khác nhau"]):
            intent = "compare_product"
        elif any(kw in q for kw in ["còn hàng", "hết hàng", "tồn kho", "stock"]):
            intent = "check_stock"
        elif any(kw in q for kw in ["tạo đơn", "order", "đặt hàng", "mua"]):
            intent = "create_order"
        elif any(kw in q for kw in ["tìm", "gợi ý", "recommend", "bán", "muốn", "nên"]):
            intent = "recommend_product"

        # Detect list_all
        list_all = any(kw in q for kw in [
            "toàn bộ", "tất cả", "danh sách đầy đủ", "liệt kê",
            "cho tôi hết", "list all", "all products", "tất cả sản phẩm"
        ])

        criteria = _postprocess_numeric_constraints(query, {
            "catalog_query_type": catalog_query_type,
            "summary": query,
            "list_all": list_all,
        })

        return {
            "intent": intent,
            "extracted_criteria": criteria,
            "error": "LLM unavailable - rule-based fallback"
        }

    @staticmethod
    def _get_llm():
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.1,
        )


class FollowUpResolver:
    """Resolve follow-up query dựa trên history + recent products bằng LLM."""

    @staticmethod
    def resolve(
        *,
        query: str,
        intent: str,
        criteria: Dict[str, Any],
        recent_products: List[Dict[str, Any]],
        history: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        if not recent_products:
            return {
                "should_resolve": False,
                "selected_indices": [],
                "reason": "Không có sản phẩm gần nhất trong history để đối chiếu.",
            }

        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(FollowUpResolution)

            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            products_text = "\n".join(
                f"{idx}. {p.get('name', 'N/A')} | SKU: {p.get('short_code') or p.get('id') or 'N/A'} | "
                f"Location: {p.get('location', 'Unknown')} | Processing: {p.get('processing_time', 'Unknown')}"
                for idx, p in enumerate(recent_products[:5], 1)
            )

            system_prompt = """Bạn là bộ giải quyết follow-up context cho hệ thống POD.

Nhiệm vụ:
- Xác định xem câu hỏi hiện tại có đang tham chiếu tới các sản phẩm vừa được assistant nhắc tới ở lượt trước hay không.
- Nếu có, chọn đúng các chỉ số sản phẩm trong danh sách recent_products.

Quy tắc:
- Chỉ được chọn từ danh sách recent_products đã cung cấp. Không bịa thêm tên hoặc SKU.
- Nếu query là follow-up kiểu "mẫu này", "các sản phẩm này", "các xưởng áo này", "those", "these", "cái vừa rồi", hãy resolve về sản phẩm phù hợp nhất trong recent_products.
- Nếu intent là compare_product và query ám chỉ nhiều sản phẩm, nên chọn 2 hoặc 3 sản phẩm theo ngữ cảnh gần nhất.
- Nếu không chắc query có tham chiếu tới recent_products hay không, trả should_resolve=false.
- Ưu tiên chính xác hơn là cố đoán.
- Trả lời hoàn toàn bằng JSON theo schema."""

            user_prompt = (
                f"Current intent: {intent}\n"
                f"Current query: {query}\n"
                f"Current criteria: {json.dumps(criteria or {}, ensure_ascii=False)}\n\n"
                f"Recent chat context:\n{history_text or '(none)'}\n\n"
                f"recent_products:\n{products_text}"
            )

            result: FollowUpResolution = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
            payload["selected_indices"] = [
                int(x) for x in (payload.get("selected_indices") or [])
                if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())
            ]
            return payload
        except Exception as e:
            logger.warning(f"FollowUpResolver failed: {e}")
            return {
                "should_resolve": False,
                "selected_indices": [],
                "reason": f"resolver_error: {e}",
            }


class ContextTaskRefiner:
    """Tinh chỉnh task dựa trên product context đã resolve từ history."""

    @staticmethod
    def refine(
        *,
        query: str,
        intent: str,
        criteria: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        if not criteria:
            return {"should_override": False, "task": "", "reason": ""}

        recent_names = criteria.get("product_names") or []
        recent_skus = criteria.get("skus") or []
        if not recent_names and not recent_skus:
            return {"should_override": False, "task": "", "reason": ""}

        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(ContextTaskRefinement)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )

            system_prompt = """Bạn là bộ tinh chỉnh task theo product context cho hệ thống POD.

Mục tiêu:
- Quyết định xem query hiện tại có đang hỏi thông tin về partner/xưởng/nhà máy của CHÍNH sản phẩm đã được resolve từ history hay không.
- Hoặc đang hỏi thông tin chi tiết của CHÍNH sản phẩm đó như màu, size, chất liệu, công nghệ in hoặc processing time.

Quy tắc:
- Chỉ override sang task `product_partner_info` khi query rõ ràng đang hỏi về partner, xưởng, nhà máy, manufacturer, factory, vendor của sản phẩm hiện tại.
- Override sang task `product_detail_info` khi query hỏi màu, size, biến thể, chất liệu, công nghệ in, processing time hoặc thông tin chi tiết của một sản phẩm cụ thể.
- Nếu query chỉ hỏi thông tin chung về toàn catalog như "có những partner nào", "danh sách partner", thì không override.
- Nếu query đang hỏi chi tiết về một sản phẩm cụ thể đã có trong criteria và nội dung xoay quanh xưởng/partner của sản phẩm đó, trả should_override=true và task=product_partner_info.
- Nếu query đang hỏi chi tiết về một sản phẩm cụ thể đã có trong criteria nhưng không xoay quanh xưởng/partner, trả should_override=true và task=product_detail_info.
- Nếu không chắc chắn, trả should_override=false.
- Chỉ trả JSON theo schema."""

            user_prompt = (
                f"Intent gốc: {intent}\n"
                f"Query hiện tại: {query}\n"
                f"Criteria hiện tại: {json.dumps(criteria, ensure_ascii=False)}\n\n"
                f"Recent chat context:\n{history_text or '(none)'}"
            )

            result: ContextTaskRefinement = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"ContextTaskRefiner failed: {e}")
            return {"should_override": False, "task": "", "reason": f"refiner_error: {e}"}


class OtherTaskManager:
    """Fallback task manager cho các query cần suy luận mở dựa trên data."""

    @staticmethod
    def should_route_to_other(
        *,
        query: str,
        intent: str,
        criteria: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        if intent in {"create_order", "product_partner_info", "product_detail_info"}:
            return {"use_other": False, "reason": ""}

        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(OtherTaskRoutingDecision)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """Bạn là bộ điều phối fallback task `other` cho hệ thống POD BurgerPrints.

Vai trò:
- Quyết định khi nào nên chuyển query sang function `other`.
- `other` là nhánh fallback dùng LLM + data để xử lý các yêu cầu lai, follow-up mở, hoặc phân tích tư vấn không khớp trọn vào function cứng.

Các function cứng hiện có:
- recommend_product
- compare_product
- check_stock
- create_order
- catalog_info
- product_detail_info
- product_partner_info
- general_inquiry

Chỉ route sang `other` khi:
- Query cần suy luận mở dựa trên dữ liệu catalog, sản phẩm hoặc context hội thoại.
- Query là follow-up mơ hồ nhưng có ý nghĩa nghiệp vụ rõ ràng, vượt quá phạm vi một function cứng.
- Query kết hợp nhiều ý như tư vấn, giải thích, đánh đổi, chiến lược, nhận định, bước tiếp theo.
- Query cần hệ thống tự quyết định có nên lấy thêm data hay không trước khi trả lời.

Không route sang `other` khi:
- Query map rõ ràng sang recommend_product, compare_product, check_stock, create_order.
- Query chỉ hỏi liệt kê catalog đơn giản như partner, màu, location, print method, price range.
- Query hỏi chi tiết của một sản phẩm cụ thể như màu, size, biến thể, chất liệu, công nghệ in, processing time, khi đó ưu tiên product_detail_info.
- Query hỏi trực tiếp xưởng/partner của một sản phẩm cụ thể, khi đó ưu tiên product_partner_info.

Nguyên tắc:
- Ưu tiên giữ task cứng nếu đã đủ rõ.
- Chỉ bật use_other=true nếu task hiện tại chưa phản ánh đúng bản chất câu hỏi.
- Trả JSON theo schema."""

            user_prompt = (
                f"Intent hiện tại: {intent}\n"
                f"Query hiện tại: {query}\n"
                f"Criteria hiện tại: {json.dumps(criteria or {}, ensure_ascii=False)}\n\n"
                f"Recent chat context:\n{history_text or '(none)'}"
            )

            result: OtherTaskRoutingDecision = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"OtherTaskManager.should_route_to_other failed: {e}")
            return {"use_other": False, "reason": f"other_router_error: {e}"}

    @staticmethod
    def plan(
        *,
        query: str,
        intent: str,
        criteria: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
        target_product: Dict[str, Any] | None = None,
        focus_products: List[Dict[str, Any]] | None = None,
        catalog_summary: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(OtherTaskPlan)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """Bạn là function `other` của hệ thống POD BurgerPrints.

Vai trò cốt lõi:
- Xử lý các query không khớp trọn với function cứng nhưng vẫn cần suy luận nghiệp vụ dựa trên dữ liệu thật.
- Không trả lời cảm tính. Luôn ưu tiên sử dụng dữ liệu hiện có, và nếu cần thì yêu cầu hệ thống lấy thêm data trước khi trả lời.
- Chỉ yêu cầu thêm thông tin từ người dùng khi dữ liệu hiện có và các data fetch khả dụng vẫn không đủ để kết luận.

Các nguồn dữ liệu có thể dùng:
- catalog hiện tại
- context hội thoại gần nhất
- sản phẩm đang focus
- nhóm sản phẩm liên quan

Các hành động bạn được chọn:
1. answer_with_current_data
   - Dùng khi dữ liệu hiện có đã đủ để trả lời.
2. fetch_variations_then_answer
   - Dùng khi cần dữ liệu cấp biến thể của một sản phẩm cụ thể như partner, màu, size, giá theo biến thể.
3. fetch_compare_details_then_answer
   - Dùng khi cần dữ liệu chi tiết để so sánh hoặc phân tích trên nhiều sản phẩm.
4. ask_user
   - Chỉ dùng khi không thể xác định đúng đối tượng cần phân tích hoặc thiếu điều kiện bắt buộc mà data hiện có không bù được.

Nguyên tắc bắt buộc:
- Ưu tiên answer_with_current_data hoặc fetch_* trước ask_user.
- Không yêu cầu thêm thông tin nếu có thể suy luận hợp lý từ history, criteria và data hiện có.
- Không bịa sản phẩm hoặc SKU không có trong context.
- Nếu query nói về follow-up như "mẫu này", "hướng này", "còn case nào tốt hơn", hãy tận dụng context.
- Trả JSON theo schema."""

            user_prompt = (
                f"Intent hiện tại: {intent}\n"
                f"Query hiện tại: {query}\n"
                f"Criteria hiện tại: {json.dumps(criteria or {}, ensure_ascii=False)}\n"
                f"Catalog summary: {json.dumps(catalog_summary or {}, ensure_ascii=False)}\n"
                f"Target product: {json.dumps(target_product or {}, ensure_ascii=False)}\n"
                f"Focus products: {json.dumps(focus_products or [], ensure_ascii=False)}\n\n"
                f"Recent chat context:\n{history_text or '(none)'}"
            )

            result: OtherTaskPlan = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"OtherTaskManager.plan failed: {e}")
            return {
                "action": "answer_with_current_data",
                "answer_goal": "Giải thích và tư vấn dựa trên dữ liệu hiện có",
                "target_product_names": criteria.get("product_names", []) if isinstance(criteria, dict) else [],
                "target_skus": criteria.get("skus", []) if isinstance(criteria, dict) else [],
                "information_needed_from_user": [],
                "reason": f"other_plan_error: {e}",
            }

    @staticmethod
    def respond(
        *,
        query: str,
        intent: str,
        criteria: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
        catalog_summary: Dict[str, Any] | None = None,
        focus_products: List[Dict[str, Any]] | None = None,
        target_product: Dict[str, Any] | None = None,
        extra_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(OtherTaskResponse)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """Bạn là function `other` của trợ lý POD BurgerPrints.

Vai trò:
- Trả lời các yêu cầu mở nhưng vẫn phải bám sát dữ liệu thật.
- Tư duy như một chuyên gia tư vấn vận hành và thương mại POD.
- Không nói về nội bộ hệ thống, prompt hay kỹ thuật triển khai.

Nguyên tắc trả lời:
- Ưu tiên kết luận rõ ràng, sau đó giải thích ngắn gọn dựa trên dữ liệu.
- Chỉ nói những gì dữ liệu hiện có hỗ trợ.
- Nếu dữ liệu vẫn chưa đủ để trả lời chính xác, hãy hỏi bổ sung thật ngắn gọn và nêu rõ cần gì.
- Không đẩy trách nhiệm cho người dùng nếu dữ liệu đã đủ.
- Dùng tiếng Việt chuyên nghiệp, dễ đọc.
- Hạn chế ký hiệu đặc biệt. Có thể dùng dấu câu và dấu gạch đầu dòng nếu cần.

Định dạng:
- Nếu đủ dữ liệu: status=answer và response là câu trả lời hoàn chỉnh.
- Nếu chưa đủ: status=ask_user và response là yêu cầu bổ sung ngắn gọn, cụ thể.
- JSON only."""

            user_prompt = (
                f"Intent hiện tại: {intent}\n"
                f"Query hiện tại: {query}\n"
                f"Criteria hiện tại: {json.dumps(criteria or {}, ensure_ascii=False)}\n"
                f"Catalog summary: {json.dumps(catalog_summary or {}, ensure_ascii=False)}\n"
                f"Target product: {json.dumps(target_product or {}, ensure_ascii=False)}\n"
                f"Focus products: {json.dumps(focus_products or [], ensure_ascii=False)}\n"
                f"Extra data: {json.dumps(extra_data or {}, ensure_ascii=False)}\n\n"
                f"Recent chat context:\n{history_text or '(none)'}"
            )

            result: OtherTaskResponse = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"OtherTaskManager.respond failed: {e}")
            return {
                "status": "ask_user",
                "response": "Mình cần thêm một chút thông tin để xử lý chính xác hơn. Bạn hãy nói rõ sản phẩm hoặc mục tiêu phân tích mà bạn muốn tập trung.",
                "missing_information": ["sản phẩm hoặc mục tiêu phân tích"],
            }


class FlowValidator:
    """LLM-based validator and replanner for task routing/output."""

    ALLOWED_TASKS = [
        "recommend_product",
        "compare_product",
        "check_stock",
        "create_order",
        "catalog_info",
        "product_detail_info",
        "product_partner_info",
        "general_inquiry",
        "other",
    ]

    @staticmethod
    def validate_routing(
        *,
        query: str,
        intent: str,
        task: str,
        route: str,
        criteria: Dict[str, Any],
        missing_fields: List[str] | None = None,
        history: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(FlowValidationDecision)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """You validate task routing for a BurgerPrints POD agent.

Decide only whether the current task and route are valid for the user query.
Return JSON only.

Available tasks:
- recommend_product: filter/rank product candidates
- compare_product: compare multiple concrete products
- check_stock: check inventory or out-of-stock status
- create_order: create an order
- catalog_info: catalog-wide listing/statistics
- product_detail_info: one product's colors/sizes/material/print/lead-time details
- product_partner_info: one product's partner/factory information
- general_inquiry: generic question without catalog data
- other: open-ended data-backed reasoning fallback

Fail when:
- task scope is broader or narrower than the actual query
- user asks for a concrete product action but task is unrelated
- route asks user for more info even though current data should be enough

Pass when:
- task matches the real intent and scope
- asking follow-up is genuinely required
- open-ended data-backed reasoning is better handled by other
"""
            user_prompt = (
                f"Query: {query}\n"
                f"Original intent: {intent}\n"
                f"Current task: {task}\n"
                f"Current route: {route}\n"
                f"Missing fields: {json.dumps(missing_fields or [], ensure_ascii=False)}\n"
                f"Criteria: {json.dumps(criteria or {}, ensure_ascii=False)}\n\n"
                f"Recent history:\n{history_text or '(none)'}"
            )
            result: FlowValidationDecision = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"FlowValidator.validate_routing failed: {e}")
            return {
                "is_valid": True,
                "reason": f"routing_validator_error: {e}",
                "missing_information": [],
            }

    @staticmethod
    def validate_output(
        *,
        query: str,
        intent: str,
        task: str,
        criteria: Dict[str, Any],
        response_msg: str,
        history: List[Dict[str, Any]] | None = None,
        data_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(FlowValidationDecision)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """You validate the final answer of a BurgerPrints POD agent.

Decide only whether the current output directly answers the user, matches the task scope,
and is consistent with the available data. Return JSON only.

Fail when the answer:
- drifts away from the asked product/market/scope
- ignores hard constraints from criteria
- asks for more information even though the current data is enough
- gives a generic answer instead of a concrete recommendation, comparison, or stock result
"""
            user_prompt = (
                f"Query: {query}\n"
                f"Original intent: {intent}\n"
                f"Current task: {task}\n"
                f"Criteria: {json.dumps(criteria or {}, ensure_ascii=False)}\n"
                f"Data snapshot: {json.dumps(data_snapshot or {}, ensure_ascii=False)}\n\n"
                f"Current output:\n{response_msg}\n\n"
                f"Recent history:\n{history_text or '(none)'}"
            )
            result: FlowValidationDecision = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        except Exception as e:
            logger.warning(f"FlowValidator.validate_output failed: {e}")
            return {
                "is_valid": True,
                "reason": f"output_validator_error: {e}",
                "missing_information": [],
            }

    @staticmethod
    def replan_task(
        *,
        query: str,
        intent: str,
        current_task: str,
        current_route: str,
        criteria: Dict[str, Any],
        history: List[Dict[str, Any]] | None = None,
        validation_reason: str = "",
        missing_information: List[str] | None = None,
        data_snapshot: Dict[str, Any] | None = None,
        response_msg: str = "",
    ) -> Dict[str, Any]:
        allowed_tasks = list(FlowValidator.ALLOWED_TASKS)

        try:
            llm = IntentAnalyzer._get_llm().with_structured_output(TaskReplanDecision)
            history_tail = history[-4:] if history else []
            history_text = "\n".join(
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in history_tail
            )
            system_prompt = """You are a reflection replanner for a BurgerPrints POD agent.

When validator says FAIL, think again and choose the most effective next action.
Do not use any banned-task or blacklist mechanism.

You may:
- keep the same task if the task is still fundamentally correct
- switch to a better task if the scope is wrong
- switch route to zorinask only if information is truly missing
- send route=data_agent when the task is clear and needs execution
- send route=task_router when the graph should reroute using the new task

Important preferences:
- If the query clearly contains market + product type + cost/price + ship/lead time + asks for partner/SKU, prefer recommend_product.
- If the query asks about colors/sizes/material/print/lead time of one concrete product, prefer product_detail_info.
- If the query asks which partner/factory serves one concrete product, prefer product_partner_info.
- Use other only for genuinely open-ended reasoning that does not fit the structured task set.

Return JSON only.
"""
            user_prompt = (
                f"Query: {query}\n"
                f"Original intent: {intent}\n"
                f"Current task: {current_task}\n"
                f"Current route: {current_route}\n"
                f"Validator reason: {validation_reason}\n"
                f"Missing information: {json.dumps(missing_information or [], ensure_ascii=False)}\n"
                f"Criteria: {json.dumps(criteria or {}, ensure_ascii=False)}\n"
                f"Data snapshot: {json.dumps(data_snapshot or {}, ensure_ascii=False)}\n"
                f"Current response: {response_msg}\n"
                f"Allowed tasks: {json.dumps(allowed_tasks, ensure_ascii=False)}\n\n"
                f"Recent history:\n{history_text or '(none)'}"
            )
            result: TaskReplanDecision = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
            chosen_task = str(payload.get("task") or "").strip()
            if chosen_task not in allowed_tasks:
                payload["task"] = current_task or intent or "recommend_product"
                payload["reason"] = (
                    f"{payload.get('reason', '')} Reflection returned an invalid task, so fallback to {payload['task']}."
                ).strip()
            chosen_route = str(payload.get("route") or "task_router").strip()
            if chosen_route not in {"task_router", "data_agent", "zorinask", "memory"}:
                payload["route"] = "task_router"
            return payload
        except Exception as e:
            logger.warning(f"FlowValidator.replan_task failed: {e}")
            fallback_route = "zorinask" if (missing_information or []) else "task_router"
            return {
                "task": current_task or intent or "recommend_product",
                "route": fallback_route,
                "reason": f"replan_error: {e}. Fallback route={fallback_route}.",
            }


# ---------------------------------------------------------------------------
# Task Router
# ---------------------------------------------------------------------------

class TaskRouter:
    """Route the execution task based on intent, criteria, and reflection."""

    @staticmethod
    def route(
        intent: str,
        criteria: Dict,
        query: str = "",
        history: List[Dict[str, Any]] | None = None,
        preferred_task: str = "",
        preferred_route: str = "",
    ) -> Dict[str, Any]:
        route_map = {
            "recommend_product": "data_agent",
            "compare_product": "data_agent",
            "check_stock": "data_agent",
            "create_order": "data_agent",
            "catalog_info": "data_agent",
            "product_detail_info": "data_agent",
            "product_partner_info": "data_agent",
            "other": "data_agent",
            "general_inquiry": "zorinask",
        }

        task = (preferred_task or criteria.get("task_override") or intent or "").strip()
        route = (preferred_route or route_map.get(task or intent, "zorinask")).strip()
        missing_fields = []
        replan_reason = ""

        if task == "compare_product":
            product_names = criteria.get("product_names", [])
            skus = criteria.get("skus", [])
            if len(product_names) < 2 and len(skus) < 2:
                missing_fields.append("product_names/skus")
        elif task == "create_order":
            required = ["product_names", "shipping_location"]
            for field in required:
                if not criteria.get(field):
                    missing_fields.append(field)
        elif task in {"product_partner_info", "product_detail_info"}:
            product_names = criteria.get("product_names", [])
            skus = criteria.get("skus", [])
            if not product_names and not skus:
                missing_fields.append("product_names/skus")

        if missing_fields:
            route = "zorinask"
            if preferred_task:
                replan_reason = "reflection_requested_missing_fields"

        logger.info(f"TaskRouter: intent={intent}, route={route}, task={task}, missing={missing_fields}")

        return {
            "route": route,
            "task": task,
            "missing_fields": missing_fields,
            "criteria": criteria,
            "replan_reason": replan_reason,
        }


class ResponseLocalizer:
    """Chuẩn hóa ngôn ngữ đầu ra theo ngôn ngữ query của user."""

    @staticmethod
    def localize(query: str, text: str) -> str:
        raw_text = (text or "").strip()
        if not raw_text:
            return raw_text

        target_language = detect_response_language(query)
        if target_language != "en":
            return raw_text

        try:
            llm = IntentAnalyzer._get_llm()
            system_prompt = """You are a response localizer for a POD assistant.

Your job:
- Convert the assistant response into natural, professional English.
- Preserve all factual data exactly as-is.
- Preserve all product names, SKU codes, prices, scores, ROI values, markdown structure, bullets, and tables.
- Do not add or remove meaning.
- Do not explain that you translated the text.
- Return only the final localized response text."""

            user_prompt = (
                f"Target language: English\n"
                f"User query: {query}\n\n"
                f"Assistant response to localize:\n{raw_text}"
            )
            result = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            localized = str(getattr(result, "content", "") or "").strip()
            return localized or raw_text
        except Exception as e:
            logger.warning(f"ResponseLocalizer.localize failed: {e}")
            return raw_text


# ---------------------------------------------------------------------------
# Zorin Ask (cho general inquiry và missing fields)
# ---------------------------------------------------------------------------

class ZorinAsk:
    """Xử lý general inquiry bằng LLM thuần túy và missing field clarification"""

    @staticmethod
    def build_message(intent: str = "", missing_fields: List[str] = None) -> str:
        missing_fields = missing_fields or []
        if missing_fields:
            labels = {
                "market/location": "thị trường hoặc khu vực fulfillment",
                "product_names/skus": "tên sản phẩm hoặc SKU cụ thể (ví dụ: Comfort Colors 1566, Bella + Canvas 3001)",
                "product_names": "tên sản phẩm cụ thể",
                "shipping_location": "địa chỉ giao hàng (quốc gia, thành phố)",
            }
            pretty = [labels.get(field, field.replace("_", " ")) for field in missing_fields]
            joined = ", ".join(pretty)
            return (
                "Mình cần thêm một chút thông tin để trả lời chính xác hơn.\n\n"
                f"- **Thiếu:** {joined}\n\n"
                "**Ví dụ câu hỏi đầy đủ hơn:**\n"
                "- `So sánh Comfort Colors 1566 với Bella + Canvas 3945`\n"
                "- `Tìm áo màu đen, partner Spire, dưới $12, ship US`\n"
                "- `Kiểm tra tồn kho cho Bella + Canvas 3001`\n"
            )
        if intent == "general_inquiry":
            return (
                "Bạn hãy nói rõ nhu cầu, mình sẽ tư vấn theo đúng workflow POD.\n\n"
                "**Mình có thể giúp:**\n"
                "- 🔍 **Tìm sản phẩm** theo market, partner, màu, budget, location\n"
                "- ⚖️ **So sánh sản phẩm** cụ thể\n"
                "- 📦 **Kiểm tra tồn kho** và đề xuất thay thế\n"
                "- 📋 **Xem danh sách partner** / loại sản phẩm / màu sắc trong catalog\n"
                "- 📋 **Tạo đơn hàng** với SKU hợp lệ\n\n"
                "**Ví dụ nhanh:**\n"
                "- `Có những partner nào trong catalog?`\n"
                "- `Tìm áo màu đen dưới $12 ship US`\n"
                "- `So sánh Gildan 5000 với Gildan 64000`\n"
            )
        return "Bạn cứ nói rõ hơn yêu cầu, mình sẽ xử lý tiếp."

    @staticmethod
    def respond(query: str, context: Dict = None) -> str:
        """Trả lời câu hỏi chung bằng LLM"""
        try:
            api_key = getattr(settings, "GEMINI_API_KEY", "")
            model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
            llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=0.3,
            )

            system_prompt = f"""Bạn là Zorin AI Assistant - trợ lý thông minh cho hệ thống POD BurgerPrints.

{API_KNOWLEDGE}

BẠN CÓ THỂ:
1. Trả lời câu hỏi về sản phẩm, giá cả, tồn kho, partner
2. Giải thích về các partner, màu sắc, phương pháp in
3. Tư vấn về thị trường, mùa vụ, xu hướng POD
4. Hướng dẫn sử dụng hệ thống BurgerPrints

HƯỚNG DẪN:
- Luôn trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp
- Dùng markdown để format khi cần (bảng, bullet points)
- Nếu cần thông tin chi tiết hơn, đề nghị user cung cấp tiêu chí cụ thể"""

            user_content = query
            if context:
                context_str = json.dumps(context, ensure_ascii=False, indent=2)
                user_content = f"Context:\n{context_str}\n\nQuery: {query}"

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]

            response = llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"ZorinAsk.respond failed: {e}")
            return "Xin lỗi, tôi gặp sự cố khi xử lý câu hỏi của bạn. Vui lòng thử lại sau."


# ---------------------------------------------------------------------------
# Catalog Info Responder - trả lời câu hỏi thông tin catalog
# ---------------------------------------------------------------------------

class CatalogInfoResponder:
    """Xây dựng response cho catalog_info intent từ catalog data thực"""

    @staticmethod
    def build_response(query_type: str, products_norm: list, query: str = "") -> str:
        """
        Trả lời câu hỏi thông tin catalog dựa trên data thực từ API.

        Args:
            query_type: partners|product_types|colors|locations|print_methods|price_range|general
            products_norm: Danh sách sản phẩm đã normalize
            query: Original user query
        """
        if not products_norm:
            return "❌ Không lấy được dữ liệu catalog. Vui lòng thử lại sau."

        if query_type == "partners":
            return CatalogInfoResponder._partners_response(products_norm, query)
        elif query_type == "product_types":
            return CatalogInfoResponder._product_types_response(products_norm, query)
        elif query_type == "colors":
            return CatalogInfoResponder._colors_response(products_norm, query)
        elif query_type == "locations":
            return CatalogInfoResponder._locations_response(products_norm, query)
        elif query_type == "print_methods":
            return CatalogInfoResponder._print_methods_response(products_norm, query)
        elif query_type == "price_range":
            return CatalogInfoResponder._price_range_response(products_norm, query)
        else:
            return CatalogInfoResponder._general_catalog_response(products_norm, query)

    @staticmethod
    def _partners_response(products: list, query: str) -> str:
        """Liệt kê tất cả partners và số sản phẩm per partner"""
        partner_count: Dict[str, int] = {}
        partner_products: Dict[str, List[str]] = {}

        for p in products:
            partners = p.get("partners") or []
            name = p.get("name", "")
            for partner in partners:
                if partner:
                    partner_count[partner] = partner_count.get(partner, 0) + 1
                    if partner not in partner_products:
                        partner_products[partner] = []
                    if name and len(partner_products[partner]) < 3:
                        partner_products[partner].append(name)

        # Fallback: parse từ variations nếu partners rỗng
        if not partner_count:
            for p in products:
                for v in (p.get("variations") or []):
                    if isinstance(v, dict):
                        pn = v.get("partner_name") or v.get("partner") or ""
                        if pn:
                            partner_count[pn] = partner_count.get(pn, 0) + 1

        if not partner_count:
            return (
                "## 🏭 Danh sách Partner trong Catalog BurgerPrints\n\n"
                f"Catalog hiện có **{len(products)}** sản phẩm.\n\n"
                "Mình chưa trích xuất được tên partner từ dữ liệu hiện tại. "
                "Thử hỏi: `Tìm sản phẩm của partner Spire` hoặc `Tìm sản phẩm Bella + Canvas`."
            )

        sorted_partners = sorted(partner_count.items(), key=lambda x: -x[1])
        total_partners = len(sorted_partners)

        lines = [
            "## 🏭 Các Partner hiện có trên BurgerPrints",
            "",
            f"*Catalog hiện có **{len(products)}** sản phẩm từ **{total_partners}** partner*",
            "",
            "| # | Partner | Số sản phẩm | Ví dụ sản phẩm |",
            "|---|---------|-------------|----------------|",
        ]

        for i, (partner, count) in enumerate(sorted_partners[:20], 1):
            examples = ", ".join(partner_products.get(partner, [])[:2])
            lines.append(f"| {i} | **{partner}** | {count} sản phẩm | {examples or '—'} |")

        if total_partners > 20:
            lines.append(f"| ... | *+{total_partners - 20} partner khác* | — | — |")

        lines += [
            "",
            "💡 **Gợi ý:** Bạn có thể tìm sản phẩm theo partner cụ thể:",
            "- `Tìm sản phẩm của Spire cho thị trường US`",
            "- `So sánh áo Bella + Canvas với Gildan`",
            "- `Sản phẩm Comfort Colors còn hàng không?`",
        ]

        return "\n".join(lines)

    @staticmethod
    def _product_types_response(products: list, query: str) -> str:
        """Liệt kê các loại sản phẩm"""
        type_count: Dict[str, int] = {}
        type_examples: Dict[str, List[str]] = {}

        KEYWORDS = {
            "Áo thun (T-shirt)": ["t-shirt", "tee", "tshirt", "unisex tee"],
            "Áo hoodie": ["hoodie", "hooded", "pullover"],
            "Áo sweatshirt": ["sweatshirt", "crewneck"],
            "Áo tank top": ["tank", "muscle"],
            "Áo polo": ["polo"],
            "Áo long sleeve": ["long sleeve", "longsleeve"],
            "Quần": ["pant", "short", "jogger"],
            "Mũ / Nón": ["hat", "cap", "beanie"],
            "Túi": ["bag", "tote", "backpack"],
            "Cốc / Mug": ["mug", "tumbler", "cup"],
            "Gối / Cushion": ["pillow", "cushion"],
            "Poster / Print": ["poster", "print", "canvas"],
            "Phụ kiện khác": [],
        }

        for p in products:
            name = (p.get("name") or "").lower()
            matched = False
            for category, keywords in KEYWORDS.items():
                if any(kw in name for kw in keywords):
                    type_count[category] = type_count.get(category, 0) + 1
                    if category not in type_examples:
                        type_examples[category] = []
                    if len(type_examples[category]) < 2:
                        type_examples[category].append(p.get("name", ""))
                    matched = True
                    break
            if not matched:
                type_count["Phụ kiện khác"] = type_count.get("Phụ kiện khác", 0) + 1

        sorted_types = sorted(type_count.items(), key=lambda x: -x[1])
        lines = [
            "## 🛍️ Các loại sản phẩm trong Catalog BurgerPrints",
            "",
            f"*Tổng cộng **{len(products)}** sản phẩm*",
            "",
            "| Loại sản phẩm | Số lượng | Ví dụ |",
            "|--------------|----------|-------|",
        ]

        for cat, count in sorted_types:
            examples = ", ".join(type_examples.get(cat, [])[:2]) or "—"
            lines.append(f"| {cat} | {count} | {examples} |")

        lines += [
            "",
            "💡 Để tìm sản phẩm phù hợp, hãy mô tả thêm: market, partner, màu sắc, ngân sách.",
        ]

        return "\n".join(lines)

    @staticmethod
    def _colors_response(products: list, query: str) -> str:
        """Liệt kê màu sắc có sẵn"""
        color_count: Dict[str, int] = {}

        for p in products:
            colors = p.get("available_colors") or []
            for color in colors:
                if color:
                    c = color.strip().lower()
                    color_count[c] = color_count.get(c, 0) + 1

        if not color_count:
            return (
                "## 🎨 Màu sắc trong Catalog\n\n"
                f"Catalog có **{len(products)}** sản phẩm.\n"
                "Màu sắc chi tiết cần xem từng sản phẩm cụ thể.\n\n"
                "💡 Hỏi: `Tìm áo màu đen, partner Spire, ship US`"
            )

        sorted_colors = sorted(color_count.items(), key=lambda x: -x[1])
        top_colors = sorted_colors[:30]

        lines = [
            "## 🎨 Màu sắc phổ biến trong Catalog",
            "",
            f"*Tìm thấy **{len(color_count)}** màu sắc khác nhau*",
            "",
        ]

        # Nhóm theo phổ biến nhất
        color_pills = " · ".join(f"**{c[0].title()}** ({c[1]})" for c in top_colors[:15])
        lines.append(color_pills)

        lines += [
            "",
            "**Màu phổ biến nhất:**",
        ]

        for color, count in top_colors[:10]:
            lines.append(f"- {color.title()}: có trong {count} sản phẩm")

        lines += [
            "",
            "💡 **Gợi ý:** `Tìm sản phẩm màu đen, partner Spire, dưới $12`",
        ]

        return "\n".join(lines)

    @staticmethod
    def _locations_response(products: list, query: str) -> str:
        """Liệt kê locations/warehouse"""
        loc_count: Dict[str, int] = {}
        loc_examples: Dict[str, List[str]] = {}

        for p in products:
            loc = p.get("location") or "Unknown"
            loc_count[loc] = loc_count.get(loc, 0) + 1
            if loc != "Unknown":
                if loc not in loc_examples:
                    loc_examples[loc] = []
                if len(loc_examples[loc]) < 3:
                    loc_examples[loc].append(p.get("name", ""))

        flags = {"US": "🇺🇸", "EU": "🇪🇺", "China": "🇨🇳", "Vietnam": "🇻🇳"}
        lines = [
            "## 📍 Kho hàng / Fulfillment Location",
            "",
            f"*Catalog có **{len(products)}** sản phẩm từ các kho hàng sau:*",
            "",
            "| Location | # Sản phẩm | Lead Time ước tính | Ví dụ |",
            "|----------|-----------|-------------------|-------|",
        ]

        lead_map = {
            "US": "2–5 ngày",
            "EU": "3–7 ngày",
            "China": "5–12 ngày",
            "Vietnam": "4–8 ngày",
            "Unknown": "Chưa xác định",
        }

        for loc, count in sorted(loc_count.items(), key=lambda x: -x[1]):
            flag = flags.get(loc, "🌐")
            lead = lead_map.get(loc, "—")
            examples = ", ".join(loc_examples.get(loc, [])[:2]) or "—"
            lines.append(f"| {flag} **{loc}** | {count} | {lead} | {examples} |")

        lines += [
            "",
            "💡 **Lọc theo kho hàng:** `Tìm sản phẩm kho US, giao hàng dưới 5 ngày`",
        ]

        return "\n".join(lines)

    @staticmethod
    def _print_methods_response(products: list, query: str) -> str:
        """Liệt kê phương pháp in"""
        pm_count: Dict[str, int] = {}
        pm_examples: Dict[str, List[str]] = {}

        for p in products:
            pm = p.get("print_method") or "Unknown"
            pm_count[pm] = pm_count.get(pm, 0) + 1
            if pm != "Unknown":
                if pm not in pm_examples:
                    pm_examples[pm] = []
                if len(pm_examples[pm]) < 3:
                    pm_examples[pm].append(p.get("name", ""))

        descriptions = {
            "DTG": "Direct-to-Garment - in trực tiếp lên vải, phù hợp thiết kế nhiều màu",
            "DTF": "Direct-to-Film - chất lượng cao, bền màu",
            "DTG/DTF": "Hỗ trợ cả DTG và DTF",
            "Sublimation": "In thăng hoa - màu sắc sống động, thường dùng cho polyester",
            "AOP": "All-Over-Print - in toàn thân sản phẩm",
            "Embroidery": "Thêu tay - cao cấp, bền lâu",
            "Hot-Transfer": "In nhiệt chuyển - phổ thông, giá rẻ",
            "Screen Print": "In lụa - phù hợp số lượng lớn, ít màu",
        }

        lines = [
            "## 🖨️ Phương pháp in trên BurgerPrints",
            "",
            f"*Catalog có **{len(products)}** sản phẩm với các công nghệ in:*",
            "",
        ]

        for pm, count in sorted(pm_count.items(), key=lambda x: -x[1]):
            if pm == "Unknown":
                continue
            desc = descriptions.get(pm, "")
            examples = ", ".join(pm_examples.get(pm, [])[:2]) or "—"
            lines.append(f"### {pm} ({count} sản phẩm)")
            if desc:
                lines.append(f"*{desc}*")
            lines.append(f"Ví dụ: {examples}")
            lines.append("")

        lines += [
            "💡 **Gợi ý:** `Tìm sản phẩm dùng DTG, kho US, dưới $12`",
        ]

        return "\n".join(lines)

    @staticmethod
    def _price_range_response(products: list, query: str) -> str:
        """Thống kê khoảng giá"""
        prices = []
        for p in products:
            pm = p.get("price_min") or p.get("base_cost") or 0
            if pm and pm > 0:
                prices.append(float(pm))

        if not prices:
            return (
                "## 💵 Khoảng giá trong Catalog\n\n"
                "Chưa trích xuất được dữ liệu giá chi tiết.\n\n"
                "💡 Hỏi: `Tìm sản phẩm dưới $12 cho thị trường US`"
            )

        prices.sort()
        min_p = min(prices)
        max_p = max(prices)
        avg_p = sum(prices) / len(prices)
        p25 = prices[int(len(prices) * 0.25)]
        p50 = prices[int(len(prices) * 0.50)]
        p75 = prices[int(len(prices) * 0.75)]

        buckets = {
            "Dưới $5": len([p for p in prices if p < 5]),
            "$5–$10": len([p for p in prices if 5 <= p < 10]),
            "$10–$15": len([p for p in prices if 10 <= p < 15]),
            "$15–$25": len([p for p in prices if 15 <= p < 25]),
            "$25+": len([p for p in prices if p >= 25]),
        }

        lines = [
            "## 💵 Khoảng giá trong Catalog BurgerPrints",
            "",
            f"*Dựa trên **{len(prices)}** sản phẩm có dữ liệu giá*",
            "",
            "| Thống kê | Giá |",
            "|----------|-----|",
            f"| Thấp nhất | **${min_p:.2f}** |",
            f"| Cao nhất | **${max_p:.2f}** |",
            f"| Trung bình | **${avg_p:.2f}** |",
            f"| 25th percentile | ${p25:.2f} |",
            f"| Median (50%) | ${p50:.2f} |",
            f"| 75th percentile | ${p75:.2f} |",
            "",
            "**Phân bố theo khoảng giá:**",
            "",
        ]

        total_priced = len(prices)
        for bucket, count in buckets.items():
            pct = count / total_priced * 100 if total_priced else 0
            bar = "█" * int(pct / 5)
            lines.append(f"- **{bucket}**: {count} sản phẩm ({pct:.0f}%) {bar}")

        lines += [
            "",
            "💡 **Gợi ý:** `Tìm sản phẩm dưới $12, kho US, partner Spire`",
        ]

        return "\n".join(lines)

    @staticmethod
    def _general_catalog_response(products: list, query: str) -> str:
        """Tổng quan catalog"""
        loc_count: Dict[str, int] = {}
        pm_count: Dict[str, int] = {}
        partner_set = set()

        for p in products:
            loc = p.get("location") or "Unknown"
            loc_count[loc] = loc_count.get(loc, 0) + 1
            pm = p.get("print_method") or "Unknown"
            pm_count[pm] = pm_count.get(pm, 0) + 1
            for partner in (p.get("partners") or []):
                if partner:
                    partner_set.add(partner)

        lines = [
            "## 📊 Tổng quan Catalog BurgerPrints",
            "",
            f"**Tổng số sản phẩm:** {len(products)}",
            f"**Số partner:** {len(partner_set)}",
            "",
            "**Phân bố theo location:**",
        ]

        for loc, cnt in sorted(loc_count.items(), key=lambda x: -x[1]):
            lines.append(f"- {loc}: {cnt} sản phẩm")

        lines += ["", "**Phân bố theo print method:**"]
        for pm, cnt in sorted(pm_count.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {pm}: {cnt} sản phẩm")

        lines += [
            "",
            "💡 **Hỏi thêm:** `Có những partner nào?` | `Khoảng giá bao nhiêu?` | `Phương pháp in nào được hỗ trợ?`",
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def extract_skus_from_names(product_names: List[str]) -> List[str]:
    """Trích xuất SKUs từ product names"""
    skus = []
    for name in product_names:
        numbers = re.findall(r'\d+', name)
        if numbers:
            skus.append(numbers[-1])
    return skus
