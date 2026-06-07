from django.urls import path
from agent import views

# REST API routes
urlpatterns = [
    path("chat/", views.ChatAPIView.as_view(), name="api-chat"),
    path("chat/stream/", views.StreamingChatAPIView.as_view(), name="api-chat-stream"),
    path("products/", views.ProductsAPIView.as_view(), name="api-products"),
    path("products/out-of-stock/", views.OutOfStockAPIView.as_view(), name="api-out-of-stock"),
    path("products/<str:product_id>/", views.ProductDetailAPIView.as_view(), name="api-product-detail"),
    path("balance/", views.BalanceAPIView.as_view(), name="api-balance"),
    # Order endpoints
    path("order/", views.OrderSubmitAPIView.as_view(), name="api-order-create"),
    path("orders/", views.OrderListAPIView.as_view(), name="api-orders-list"),
    path("orders/charge/", views.OrderChargeAPIView.as_view(), name="api-orders-charge"),
    path("orders/<str:order_id>/", views.OrderDetailAPIView.as_view(), name="api-orders-detail"),
    # Other
    path("history/<str:session_id>/", views.ConversationHistoryAPIView.as_view(), name="api-history"),
    path("graph-definition/", views.GraphDefinitionAPIView.as_view(), name="api-graph-definition"),
    path("cache/stats/", views.CacheStatsAPIView.as_view(), name="api-cache-stats"),
]
