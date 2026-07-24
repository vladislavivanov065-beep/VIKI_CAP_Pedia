from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.articles.models import Article
from apps.assistant import services
from apps.assistant.exceptions import AssistantNotConfiguredError, AssistantRequestError


@require_POST
def ask_question(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Некорректный запрос."}, status=400)

    question = str(payload.get("question", "")).strip()
    slug = str(payload.get("article_slug", "")).strip()
    if not question:
        return JsonResponse({"error": "Введите вопрос."}, status=400)
    if not slug:
        return JsonResponse({"error": "Не указана статья."}, status=400)

    article = get_object_or_404(Article, slug=slug, is_archived=False)

    try:
        result = services.answer_question(article=article, question=question)
    except AssistantNotConfiguredError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except AssistantRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    return JsonResponse({"answer": result.answer})
