"""
Django REST API Views cho BurgerPrintsAgent
"""
import uuid
import json
import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from agent.models import Conversation, Message
from agent.graph.graph import run_agent, GRAPH_DEFINITION
from agent.services import burgerprints as bp_api
from agent.services.html_parser import normalize_product

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

        # Lấy hoặc tạo conversation
        conversation, _ = Conversation.objects.get_or_create(session_id=session_id)

        # Lưu user message
        Message.objects.create(
            conversation=conversation,
            role="user",
            content=query,
        )

        # Lấy history
        history_qs = conversation.messages.order_by("created_at")[:20]
        history = [{"role": m.role, "content": m.content} for m in history_qs]

        # Chạy agent
        result = run_agent(
            query=query,
            session_id=session_id,
            conversation_history=history,
        )

        response_msg = result.get("response_msg", "")
        intent = result.get("intent", "")

        # Lưu assistant message
        Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=response_msg,
            intent=intent,
            metadata={
                "scores": _serialize_scores(result.get("scores", [])),
                "reasons": result.get("reasons", []),
            },
        )

        return Response({
            "response": response_msg,
            "intent": intent,
            "products": _serialize_scores(result.get("scores", []))[:5],
            "reasons": result.get("reasons", []),
            "winner": _serialize_product(result.get("winner")),
            "alternatives": [_serialize_product(p) for p in result.get("alternatives", [])[:3]],
            "market_context": result.get("market_context", {}),
            "season_context": result.get("season_context", {}),
            "weather_context": result.get("weather_context", {}),
            "evidence": result.get("evidence", []),
            "validation_errors": result.get("validation_errors", []),
            "error": result.get("error", ""),
            "node_trace": result.get("node_trace", []),
        })


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
            return Response(normalize_product(data))
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
    """GET /api/balance/ - Health check kết nối BurgerPrints API"""

    def get(self, request):
        try:
            # Dùng product list (limit=1) để kiểm tra kết nối API
            products = bp_api.get_products(limit=1)
            return Response({
                "status": "ok",
                "api_connected": True,
                "product_count": len(products),
            })
        except Exception as e:
            return Response(
                {"status": "error", "api_connected": False, "error": str(e)},
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
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ]
            return Response({"messages": data, "session_id": session_id})
        except Conversation.DoesNotExist:
            return Response({"messages": [], "session_id": session_id})


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


class GraphDefinitionAPIView(APIView):
    """GET /api/graph-definition/ - Graph structure for ReactFlow"""

    def get(self, request):
        return Response(GRAPH_DEFINITION)
