from django.urls import path

from apps.assistant import views

app_name = "assistant"

urlpatterns = [
    path("ask/", views.ask_question, name="ask"),
    path("toggle/", views.toggle_assistant, name="toggle"),
    path("local-ai/", views.local_ai_admin, name="local_ai_admin"),
    path("local-ai/retrain/", views.retrain_local_ai, name="retrain_local_ai"),
    path("local-ai/status/", views.local_ai_status, name="local_ai_status"),
]
