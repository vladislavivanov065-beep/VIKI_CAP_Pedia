from django.urls import path

from apps.assistant import views

app_name = "assistant"

urlpatterns = [
    path("ask/", views.ask_question, name="ask"),
    path("toggle/", views.toggle_assistant, name="toggle"),
]
