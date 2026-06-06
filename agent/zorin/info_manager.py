"""
Zorin Info Manager - Phân tích intent và routing tasks
Chứa IntentAnalyzer, TaskRouter, ZorinAsk

Intent types mở rộng:
- recommend_product: Tìm / gợi ý sản phẩm
- compare_product: So sánh sản phẩm
- check_stock: Kiểm tra tồn kho
- create_order: Tạo đơn hàng
- catalog_info: Hỏi thông tin catalog (partner nào có?, loại sản phẩm?, giá range?, ...)
- general_inquiry: Câu hỏi chung về POD, không cần catalog
"""
import json
import re
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Knowledge từ BurgerPrintAPI.md
# ---------------------------------------------------------------------------
API_KNOWLEDGE = """
BURGERPRINTS API V2.0 - KIẾN THỨC VỀ ENDPOINTS VÀ DATA FIELDS

CÁC ENDPOINTS CHÍNH:
1. /v2/authenticated - Kiểm tra API key
2. /v2/order - Quản lý đơn hàng (GET all, GET single, POST create, PUT cancel)
3. /v2/product - Quản lý sản phẩm (GET danh sách, GET chi tiết theo short_code)
4. /v2/product/out-of-stock - Sản phẩm hết hàng
5. /v2/product/{short_code} - Chi tiết sản phẩm theo mã
6. /v2/balance - Kiểm tra số dư tài khoản
7. /v2/webhook - Quản lý webhook

CÁC FIELD QUAN TRỌNG TRONG PRODUCT DATA:
- short_code: Mã sản phẩm duy nhất (ví dụ: "A33378-85812848c41746f3952e3881ca8fe96f")
- name: Tên sản phẩm (ví dụ: "Comfort Colors 1566", "Gildan 5000", "Bella + Canvas 3001")
- html_desc: Mô tả HTML chứa thông tin chi tiết (location, material, print method, processing time)
- price / base_cost: Giá vốn / giá bán
- margin: Biên lợi nhuận
- partner / partner_name: Đối tác sản xuất (ví dụ: "Spire", "Bella + Canvas", "Gildan", "Comfort Colors")
- colors / available_colors: Danh sách màu sắc có sẵn
- sizes / available_sizes: Danh sách kích thước có sẵn
- print_method: Phương pháp in (DTG, Sublimation, DTF, AOP, Embroidery, ...)
- location: Vị trí kho hàng (US, EU, China, Vietnam)
- processing_time: Thời gian xử lý (ví dụ: "2-5 business days")
- inventory: Tình trạng tồn kho

CÁC PARTNERS PHỔ BIẾN TRÊN BURGERPRINTS:
- Spire, Bella + Canvas, Gildan, Comfort Colors, Next Level, Port & Company
- District, Anvil, American Apparel, Delta Pro Weight, Hanes, Jerzees
- Lane Seven, Alternative Apparel, LAT Apparel

CÁC FILTER CÓ THỂ ÁP DỤNG:
1. Theo partner: Lọc sản phẩm theo đối tác sản xuất
2. Theo color: Lọc theo màu sắc
3. Theo price range: Lọc theo khoảng giá (min_price, max_price)
4. Theo location: Lọc theo vị trí kho hàng (US, EU, China, Vietnam)
5. Theo print_method: Lọc theo phương pháp in
6. Theo market: Lọc theo thị trường mục tiêu
7. Theo inventory: Lọc theo tình trạng tồn kho
8. Theo processing time: Lọc theo tốc độ xử lý
"""

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class IntentCriteria(BaseModel):
    """Schema output từ IntentAnalyzer - mở rộng với catalog_info intent"""
    intent: str = Field(
        description=(
            "One of: recommend_product | compare_product | check_stock | create_order "
            "| catalog_info | general_inquiry. "
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

6. **general_inquiry**: Câu hỏi chung về POD không cần catalog
   - "POD là gì?"
   - "Làm sao để bắt đầu bán POD?"
   - "Phí ship như thế nào?"

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
    "skus": ["mã_SKU_1"],
    "shipping_location": "địa_chỉ_giao_hàng",
    "print_tech": "công_nghệ_in",
    "quantity": số_lượng_nếu_có,
    "size_preference": "size_nếu_có"
}}

VÍ DỤ:
- "hiện tại đang có những partner nào" → intent: catalog_info, catalog_query_type: partners
- "Tìm áo màu đen, partner Spire, dưới $12 ship US" → intent: recommend_product, partner_preference: ["Spire"], color_preference: ["black"], max_price: 12.0, location_preference: "US"
- "So sánh Comfort Colors 1566 với Bella + Canvas 3945" → intent: compare_product, product_names: ["Comfort Colors 1566", "Bella + Canvas 3945"]
- "Còn hàng áo hoodie màu xanh không?" → intent: check_stock, product_names: ["hoodie"], color_preference: ["blue"]

CHÚ Ý:
- Ưu tiên catalog_info khi câu hỏi mang tính liệt kê/thống kê về catalog
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

        return {
            "intent": intent,
            "extracted_criteria": {"catalog_query_type": catalog_query_type, "summary": query, "list_all": list_all},
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


# ---------------------------------------------------------------------------
# Task Router
# ---------------------------------------------------------------------------

class TaskRouter:
    """Điều hướng task dựa trên intent và criteria"""

    @staticmethod
    def route(intent: str, criteria: Dict, query: str = "") -> Dict[str, Any]:
        """
        Xác định route và task cần thực hiện

        Routes:
        - "data_agent": cần lấy catalog data
        - "zorinask": cần clarification hoặc general answer
        """
        route_map = {
            "recommend_product": "data_agent",
            "compare_product": "data_agent",
            "check_stock": "data_agent",
            "create_order": "data_agent",
            "catalog_info": "data_agent",   # ← cần catalog để trả lời
            "general_inquiry": "zorinask",
        }

        route = route_map.get(intent, "zorinask")
        task = intent  # task = intent directly
        missing_fields = []

        if intent == "recommend_product":
            # Không bắt buộc phải có market - agent tự infer được
            pass

        elif intent == "compare_product":
            product_names = criteria.get("product_names", [])
            skus = criteria.get("skus", [])
            if len(product_names) < 2 and len(skus) < 2:
                missing_fields.append("product_names/skus")

        elif intent == "check_stock":
            # Không bắt buộc - kiểm tra all products cũng được
            pass

        elif intent == "create_order":
            required = ["product_names", "shipping_location"]
            for field in required:
                if not criteria.get(field):
                    missing_fields.append(field)

        elif intent == "catalog_info":
            # Luôn route đến data_agent - không cần clarification
            pass

        # Chỉ route zorinask nếu thiếu field quan trọng
        if missing_fields:
            route = "zorinask"

        logger.info(f"TaskRouter: intent={intent}, route={route}, task={task}, missing={missing_fields}")

        return {
            "route": route,
            "task": task,
            "missing_fields": missing_fields,
            "criteria": criteria
        }


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
