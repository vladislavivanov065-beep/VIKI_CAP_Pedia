from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.search.services import search_suggestions, search_with_snippets, suggest_correction


def search_results(request):
    query = request.GET.get("q", "").strip()
    results = []
    suggestion = None
    if query:
        results = search_with_snippets(query)
        if not results:
            suggestion = suggest_correction(query)

    return render(
        request,
        "search/results.html",
        {"query": query, "results": results, "suggestion": suggestion},
    )


def search_suggestions_view(request):
    query = request.GET.get("q", "")
    suggestions = [
        {"title": article.title, "url": reverse("articles:detail", kwargs={"slug": article.slug})}
        for article in search_suggestions(query)
    ]
    return JsonResponse({"suggestions": suggestions})
