from django.urls import path
from agent import views

# Web routes (Templates)
urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("graph/", views.graph_view, name="graph"),
]
