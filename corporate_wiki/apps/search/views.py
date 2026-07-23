from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.search.services import extract_snippet, search_articles, search_suggestions


def search_results(request):
    query = request.GET.get("q", "").strip()
    results = []
    if query:
        for article in search_articles(query):
            revision = article.current_revision
            snippet = extract_snippet(revision.content_source, query) if revision else ""
            results.append({"article": article, "revision": revision, "snippet": snippet})

    return render(request, "search/results.html", {"query": query, "results": results})


def search_suggestions_view(request):
    query = request.GET.get("q", "")
    suggestions = [
        {"title": article.title, "url": reverse("articles:detail", kwargs={"slug": article.slug})}
        for article in search_suggestions(query)
    ]
    return JsonResponse({"suggestions": suggestions})
