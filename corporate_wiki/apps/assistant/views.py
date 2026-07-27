from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.articles.models import Article
from apps.assistant import services, training
from apps.assistant.exceptions import (
    AssistantDisabledError,
    AssistantNotConfiguredError,
    AssistantRequestError,
)
from apps.assistant.models import AssistantSettings


@require_POST
def ask_question(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Некорректный запрос."}, status=400)

    question = str(payload.get("question", "")).strip()
    slug = str(payload.get("article_slug", "")).strip()
    use_chatgpt = bool(payload.get("use_chatgpt", False))
    if not question:
        return JsonResponse({"error": "Введите вопрос."}, status=400)
    if not slug:
        return JsonResponse({"error": "Не указана статья."}, status=400)

    article = get_object_or_404(Article, slug=slug, is_archived=False)

    try:
        if use_chatgpt:
            result = services.answer_question(article=article, question=question)
            source = "chatgpt"
        else:
            result = services.answer_question_locally(article=article, question=question)
            source = "local"
    except AssistantDisabledError as exc:
        return JsonResponse({"error": str(exc)}, status=403)
    except AssistantNotConfiguredError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except AssistantRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    return JsonResponse({"answer": result.answer, "source": source})


@require_POST
def toggle_assistant(request):
    if not request.user.is_staff:
        raise PermissionDenied

    enabled = request.POST.get("assistant_enabled") == "on"
    services.set_assistant_enabled(enabled=enabled, actor=request.user)
    messages.success(request, "ИИ-ассистент включён." if enabled else "ИИ-ассистент выключен.")

    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(referer)
    return redirect("home")


def local_ai_admin(request):
    if not request.user.is_staff:
        raise PermissionDenied

    return render(request, "assistant/local_ai_admin.html", {"solo": AssistantSettings.get_solo()})


@require_POST
def retrain_local_ai(request):
    if not request.user.is_staff:
        raise PermissionDenied

    try:
        training.retrain_local_model(actor=request.user)
    except training.LocalAiAlreadyTrainingError as exc:
        messages.error(request, str(exc))
        return redirect("assistant:local_ai_admin")

    solo = AssistantSettings.get_solo()
    if solo.local_ai_last_error:
        messages.error(request, f"Обучение завершилось с ошибкой: {solo.local_ai_last_error}")
    else:
        messages.success(
            request,
            f"Локальный ИИ обучен на {solo.local_ai_article_count} статьях "
            f"({solo.local_ai_chunk_count} фрагментов).",
        )
    return redirect("assistant:local_ai_admin")
