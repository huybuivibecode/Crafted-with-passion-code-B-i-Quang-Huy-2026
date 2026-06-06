from django.urls import path
from agent import views

# REST API routes
urlpatterns = [
    path("chat/", views.ChatAPIView.as_view(), name="api-chat"),
    path("products/", views.ProductsAPIView.as_view(), name="api-products"),
    path("products/out-of-stock/", views.OutOfStockAPIView.as_view(), name="api-out-of-stock"),
    path("products/<str:product_id>/", views.ProductDetailAPIView.as_view(), name="api-product-detail"),
    path("balance/", views.BalanceAPIView.as_view(), name="api-balance"),
    path("order/", views.OrderSubmitAPIView.as_view(), name="api-order"),
    path("history/<str:session_id>/", views.ConversationHistoryAPIView.as_view(), name="api-history"),
    path("graph-definition/", views.GraphDefinitionAPIView.as_view(), name="api-graph-definition"),
    path("cache/stats/", views.CacheStatsAPIView.as_view(), name="api-cache-stats"),
]
