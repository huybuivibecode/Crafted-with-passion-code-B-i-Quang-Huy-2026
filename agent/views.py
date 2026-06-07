"""
Django REST API Views cho BurgerPrintsAgent
"""
import uuid
import json
import re
import logging
import threading

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from agent.models import Conversation
from agent.graph.graph import GRAPH_DEFINITION
from agent.zorin import handle_chat
from agent.zorin.language import detect_response_language
from agent.services import burgerprints as bp_api
from agent.services.html_parser import normalize_product
from agent.services.catalog_store import normalize_catalog_product
from agent.services.catalog_cache import get_cache_stats, invalidate_products_cache, invalidate_oos_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Web Views (Templates)
# ---------------------------------------------------------------------------

def chat_view(request):
    """Trang chat chính"""
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    return render(request, "agent/chat.html", {"session_id": session_id})


def graph_view(request):
    """Trang Graph Visualization"""
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    return render(request, "agent/graph.html", {
        "session_id": session_id,
        "graph_def": json.dumps(GRAPH_DEFINITION),
    })


# ---------------------------------------------------------------------------
# API Views (REST)
# ---------------------------------------------------------------------------

class ChatAPIView(APIView):
    """
    POST /api/chat/
    Body: {"query": "...", "session_id": "..."}
    """

    def post(self, request):
        query = request.data.get("query", "").strip()
        session_id = request.data.get("session_id", str(uuid.uuid4()))

        if not query:
            return Response(
                {"error": "Query không được để trống"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = handle_chat(query=query, session_id=session_id)

        response_msg = result.get("response_msg", "")
        intent = result.get("intent", "")
        scores_raw = result.get("scores", [])

        criteria = result.get("extracted_criteria") or {}
        list_all = bool(criteria.get("list_all", False))
        requested_count = 0
        try:
            m = re.search(r"\b(\d{1,3})\b\s*(?:sản\s*phẩm|sp)\b", (query or "").lower())
            if m:
                requested_count = int(m.group(1))
        except Exception:
            requested_count = 0

        if requested_count > 0 and intent == "recommend_product":
            product_limit = min(requested_count, 200)
        elif list_all:
            product_limit = 200
        elif intent == "catalog_info":
            product_limit = 20
        elif intent == "recommend_product" and 0 < requested_count <= 50:
            product_limit = requested_count
        else:
            product_limit = 5
        products = _serialize_scores(scores_raw)[:product_limit]

        winner = _serialize_product(result.get("winner"))
        alternatives = [_serialize_product(p) for p in result.get("alternatives", [])[:3]]
        follow_ups = _build_follow_ups(
            intent=intent,
            query=query,
            products=products,
            winner=winner,
            alternatives=alternatives,
        )

        return Response({
            "session_id": session_id,
            "query": query,
            "response": response_msg,
            "intent": intent,
            "list_all": list_all,
            "total_products": len(scores_raw),
            "products": products,
            "reasons": result.get("reasons", []),
            "winner": winner,
            "alternatives": alternatives,
            "follow_ups": follow_ups,
            "market_context": result.get("market_context", {}),
            "season_context": result.get("season_context", {}),
            "weather_context": result.get("weather_context", {}),
            "applied_filters": result.get("applied_filters", []),
            "returned_objects": result.get("returned_objects", []),
            "evidence": result.get("evidence", []),
            "validation_errors": result.get("validation_errors", []),
            "error": result.get("error", ""),
            "node_trace": result.get("node_trace", []),
        })


class StreamingChatAPIView(View):
    """
    POST /api/chat/stream/
    Server-Sent Events streaming: stream response tokens dần dần.
    Strategy: run handle_chat in a thread, then stream tokens as they generate,
    finishing with a done event.
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
        except Exception:
            body = {}

        query = str(body.get('query', '')).strip()
        session_id = body.get('session_id', str(uuid.uuid4()))

        if not query:
            def err_gen():
                yield 'data: ' + json.dumps({'type': 'error', 'message': 'Query empty'}) + '\n\n'
            return StreamingHttpResponse(err_gen(), content_type='text/event-stream')

        import queue
        from agent.graph.nodes import register_stream_queue, unregister_stream_queue

        q = queue.Queue()
        register_stream_queue(session_id, q)

        def sse_generator():
            exc_holder = [None]
            result = {}

            def run():
                try:
                    res = handle_chat(query=query, session_id=session_id)
                    result.update(res)

                    # Compute final serialized payload once execution is complete
                    response_msg = result.get('response_msg', '') or ''
                    intent = result.get('intent', '')
                    scores_raw = result.get('scores', [])

                    criteria = result.get('extracted_criteria') or {}
                    list_all = bool(criteria.get('list_all', False))
                    try:
                        m_match = re.search(r'\b(\d{1,3})\b\s*(?:sản\s*phẩm|sp)\b', (query or '').lower())
                        requested_count = int(m_match.group(1)) if m_match else 0
                    except Exception:
                        requested_count = 0

                    if requested_count > 0 and intent == 'recommend_product':
                        product_limit = min(requested_count, 200)
                    elif list_all:
                        product_limit = 200
                    elif intent == 'catalog_info':
                        product_limit = 20
                    else:
                        product_limit = 5

                    products = _serialize_scores(scores_raw)[:product_limit]
                    winner = _serialize_product(result.get('winner'))
                    alternatives = [_serialize_product(p) for p in result.get('alternatives', [])[:3]]
                    follow_ups = _build_follow_ups(
                        intent=intent, query=query,
                        products=products, winner=winner, alternatives=alternatives,
                    )

                    done_payload = {
                        'type': 'done',
                        'session_id': session_id,
                        'query': query,
                        'response': response_msg,
                        'intent': intent,
                        'list_all': list_all,
                        'total_products': len(scores_raw),
                        'products': products,
                        'reasons': result.get('reasons', []),
                        'winner': winner,
                        'alternatives': alternatives,
                        'follow_ups': follow_ups,
                        'applied_filters': result.get('applied_filters', []),
                        'returned_objects': result.get('returned_objects', []),
                        'error': result.get('error', ''),
                    }
                    q.put(done_payload)
                except Exception as e:
                    exc_holder[0] = e
                    q.put({'type': 'error', 'message': str(e)})
                finally:
                    q.put(None)

            t = threading.Thread(target=run, daemon=True)
            t.start()

            while True:
                try:
                    item = q.get(timeout=60)
                    if item is None:
                        break
                    if isinstance(item, dict) and item.get('type') == 'error':
                        yield 'data: ' + json.dumps(item) + '\n\n'
                        break
                    elif isinstance(item, dict) and item.get('type') == 'done':
                        yield 'data: ' + json.dumps(item) + '\n\n'
                    else:
                        # Yield token
                        yield 'data: ' + json.dumps({'type': 'token', 'text': item}) + '\n\n'
                except queue.Empty:
                    break

            unregister_stream_queue(session_id)
            yield 'data: [DONE]\n\n'

        response = StreamingHttpResponse(sse_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response



class ProductsAPIView(APIView):
    """GET /api/products/ - Lấy catalog đã normalize"""

    def get(self, request):
        try:
            data = bp_api.get_products(limit=500)
            raw_list = data.get("data", []) if isinstance(data, dict) else data
            products = [normalize_product(p) for p in raw_list]
            return Response({"products": products, "count": len(products)})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class ProductDetailAPIView(APIView):
    """GET /api/products/<id>/ - Chi tiết sản phẩm"""

    def get(self, request, product_id):
        try:
            data = bp_api.get_product_detail(product_id)
            return Response(normalize_catalog_product(data))
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class OutOfStockAPIView(APIView):
    """GET /api/products/out-of-stock/ - Kiểm tra tồn kho"""

    def get(self, request):
        try:
            data = bp_api.get_out_of_stock()
            return Response(data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class BalanceAPIView(APIView):
    """GET /api/balance/ - Số dư tài khoản + health check"""

    def get(self, request):
        try:
            auth_data = bp_api.get_authenticated()
            is_valid = auth_data.get("is_success", False)

            result = {
                "status": "ok" if is_valid else "auth_failed",
                "api_connected": is_valid,
                "message": auth_data.get("message", ""),
            }

            if is_valid:
                try:
                    balance_data = bp_api.get_balance()
                    balance_body = balance_data.get("data", balance_data) if isinstance(balance_data, dict) else {}
                    result["balance"] = balance_body
                except Exception as be:
                    result["balance_error"] = str(be)

            return Response(result)
        except Exception as e:
            return Response(
                {"status": "error", "api_connected": False, "error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


# ---------------------------------------------------------------------------
# Order API Views
# ---------------------------------------------------------------------------

class OrderSubmitAPIView(APIView):
    """
    POST /api/order/ - Tạo đơn hàng thực sự qua BurgerPrints API
    Body: {order payload theo BurgerPrints spec}
    """

    def post(self, request):
        payload = request.data
        if not payload:
            return Response(
                {"error": "Order payload không được để trống"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        required_keys = ["shipping", "items"]
        missing = [k for k in required_keys if k not in payload]
        if missing:
            return Response(
                {"error": f"Thiếu các trường bắt buộc: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = bp_api.create_order(payload)
            return Response({"success": True, "order": result})
        except Exception as e:
            logger.error(f"OrderSubmitAPIView error: {e}")
            return Response(
                {"error": f"Không thể tạo đơn hàng: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class OrderListAPIView(APIView):
    """GET /api/orders/ - Danh sách đơn hàng"""

    def get(self, request):
        page = int(request.query_params.get("page", 1))
        limit = int(request.query_params.get("limit", 20))
        try:
            result = bp_api.get_orders(page=page, limit=limit)
            return Response(result)
        except Exception as e:
            logger.error(f"OrderListAPIView error: {e}")
            return Response(
                {"error": f"Không thể lấy danh sách đơn hàng: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class OrderDetailAPIView(APIView):
    """
    GET    /api/orders/<order_id>/ - Chi tiết đơn hàng
    DELETE /api/orders/<order_id>/ - Xoá đơn hàng (chỉ unpaid)
    """

    def get(self, request, order_id):
        try:
            result = bp_api.get_order_detail(order_id)
            return Response(result)
        except Exception as e:
            logger.error(f"OrderDetailAPIView.get error: {e}")
            return Response(
                {"error": f"Không thể lấy chi tiết đơn hàng: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def delete(self, request, order_id):
        try:
            result = bp_api.delete_order(order_id)
            return Response(result)
        except Exception as e:
            logger.error(f"OrderDetailAPIView.delete error: {e}")
            return Response(
                {"error": f"Không thể xóa đơn hàng: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class OrderChargeAPIView(APIView):
    """POST /api/orders/charge/ - Thanh toán đơn hàng"""

    def post(self, request):
        order_ids = request.data.get("order_ids", [])
        if not order_ids:
            return Response(
                {"error": "order_ids không được để trống"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(order_ids, str):
            order_ids = [order_ids]
        try:
            result = bp_api.charge_order(order_ids)
            return Response(result)
        except Exception as e:
            logger.error(f"OrderChargeAPIView error: {e}")
            return Response(
                {"error": f"Không thể charge đơn hàng: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class ConversationHistoryAPIView(APIView):
    """GET /api/history/<session_id>/ - Lịch sử hội thoại"""

    def get(self, request, session_id):
        try:
            conversation = Conversation.objects.get(session_id=session_id)
            messages = conversation.messages.all().order_by("created_at")
            data = [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "intent": m.intent,
                    "metadata": _serialize_message_metadata(m.metadata),
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ]
            return Response({"messages": data, "session_id": session_id})
        except Conversation.DoesNotExist:
            return Response({"messages": [], "session_id": session_id})


class CacheStatsAPIView(APIView):
    """GET /api/cache/stats/ - Thông tin trạng thái cache"""

    def get(self, request):
        return Response(get_cache_stats())

    def delete(self, request):
        """Xoá cache để force refresh catalog"""
        invalidate_products_cache()
        invalidate_oos_cache()
        return Response({"message": "Cache đã được xoá. Catalog sẽ được tải lại từ BurgerPrints API."})


class GraphDefinitionAPIView(APIView):
    """GET /api/graph-definition/ - Graph structure for visualization"""

    def get(self, request):
        return Response(GRAPH_DEFINITION)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_product(product: dict) -> dict:
    if not product:
        return {}
    return {
        "id": product.get("id", ""),
        "name": product.get("name", ""),
        "short_code": product.get("short_code", ""),
        "location": product.get("location", "Unknown"),
        "processing_time": product.get("processing_time", "Unknown"),
        "processing_min": product.get("processing_min", 999),
        "print_method": product.get("print_method", "Unknown"),
        "material": product.get("material", "Unknown"),
        "base_cost": product.get("base_cost", 0),
        "suggested_selling_price": product.get("suggested_selling_price", 0),
        "margin": product.get("margin", 0),
        "profit": product.get("profit", 0),
        "roi": product.get("roi", 0),
        "expected_revenue": product.get("expected_revenue", 0),
        "recommended_audience": product.get("recommended_audience", ""),
        "risks": product.get("risks", []),
        "category": product.get("category", ""),
        "inventory_status": product.get("inventory_status", "unknown"),
        "sku_valid": product.get("sku_valid", False),
        "thumbnail": product.get("thumbnail", ""),
        "partners": product.get("partners", []),
        "partner_prices": product.get("partner_prices", {}),
        "price_min": product.get("price_min", 0),
        "price_max": product.get("price_max", 0),
        "partner_summary": product.get("partner_summary", []),
        "available_colors": product.get("available_colors", []),
        "colors_count": product.get("colors_count", 0),
    }


def _serialize_message_metadata(metadata: dict) -> dict:
    metadata = metadata or {}
    scores = metadata.get("scores", []) or []
    serialized_scores = []
    for item in scores[:5]:
        if isinstance(item, dict) and "product" in item:
            serialized_scores.append({
                **_serialize_product(item.get("product", {})),
                "score": item.get("score", 0),
                "breakdown": item.get("breakdown", {}),
                "evidence": item.get("evidence", {}),
            })
        elif isinstance(item, dict):
            serialized_scores.append(item)
    returned_objects = []
    for item in (metadata.get("returned_objects", []) or [])[:12]:
        if not isinstance(item, dict):
            continue
        product = item.get("product", {}) if isinstance(item.get("product"), dict) else {}
        returned_objects.append({
            "source": item.get("source", ""),
            "product": _serialize_product(product),
        })
    return {
        "scores": serialized_scores,
        "reasons": metadata.get("reasons", []) or [],
        "winner": _serialize_product(metadata.get("winner") or {}),
        "alternatives": [_serialize_product(p) for p in (metadata.get("alternatives", []) or [])[:3]],
        "returned_objects": returned_objects,
        "applied_filters": metadata.get("applied_filters", []) or [],
        "validation_errors": metadata.get("validation_errors", []) or [],
    }


def _serialize_scores(scores: list) -> list:
    result = []
    for item in scores:
        p = item.get("product", {})
        result.append({
            **_serialize_product(p),
            "score": item.get("score", 0),
            "breakdown": item.get("breakdown", {}),
            "evidence": item.get("evidence", {}),
        })
    return result


def _build_follow_ups(intent: str, query: str, products: list, winner: dict, alternatives: list) -> list:
    """Tạo gợi ý follow-up theo cùng ngôn ngữ với query."""
    suggestions = []
    language = detect_response_language(query)
    top_product = winner or (products[0] if products else {})
    second_product = products[1] if len(products) > 1 else {}

    if language == "en":
        if intent == "recommend_product":
            if top_product.get("name"):
                suggestions.append(f"Analyze {top_product['name']} in more detail")
                suggestions.append(f"Check stock for {top_product['name']}")
            if top_product.get("name") and second_product.get("name"):
                suggestions.append(f"Compare {top_product['name']} with {second_product['name']}")
            suggestions.append("Filter further by partner, color, and budget")
        elif intent == "compare_product":
            if top_product.get("name"):
                suggestions.append("Which product is a better fit for the US market?")
                suggestions.append(f"Check stock for {top_product['name']}")
            suggestions.append("Compare them further by partner, color, and price range")
        elif intent == "check_stock":
            if alternatives:
                suggestions.append(f"Find a similar alternative to {alternatives[0].get('name', 'this product')}")
            suggestions.append("Filter in-stock products by partner and location")
        elif intent in ("create_order", "list_orders", "order_detail"):
            suggestions.append("Check my order list")
            suggestions.append("Find more products to add to the order")
        else:
            suggestions.extend([
                "Recommend 3 POD products that are easiest to sell",
                "Compare 2 products by price, colors, and partner",
                "Find products under $12 for the US market",
            ])
    else:
        if intent == "recommend_product":
            if top_product.get("name"):
                suggestions.append(f"Phân tích kỹ hơn {top_product['name']}")
                suggestions.append(f"Kiểm tra tồn kho cho {top_product['name']}")
            if top_product.get("name") and second_product.get("name"):
                suggestions.append(f"So sánh {top_product['name']} với {second_product['name']}")
            suggestions.append("Lọc thêm theo partner, màu sắc và ngân sách")
        elif intent == "compare_product":
            if top_product.get("name"):
                suggestions.append("Sản phẩm nào phù hợp thị trường US hơn trong các mẫu này?")
                suggestions.append(f"Kiểm tra tồn kho cho {top_product['name']}")
            suggestions.append("So sánh thêm theo partner, màu sắc và khoảng giá")
        elif intent == "check_stock":
            if alternatives:
                suggestions.append(f"Tìm sản phẩm thay thế giống {alternatives[0].get('name', 'sản phẩm này')}")
            suggestions.append("Lọc sản phẩm còn hàng theo partner và location")
        elif intent in ("create_order", "list_orders", "order_detail"):
            suggestions.append("Xem danh sách đơn hàng của tôi")
            suggestions.append("Tìm thêm sản phẩm để thêm vào đơn")
        else:
            suggestions.extend([
                "Gợi ý 3 sản phẩm POD dễ bán tốt nhất",
                "So sánh 2 sản phẩm theo giá, màu sắc và partner",
                "Tìm sản phẩm dưới $12 cho thị trường US",
            ])

    unique = []
    seen = set()
    for item in suggestions:
        key = item.strip().lower()
        if item and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:4]
