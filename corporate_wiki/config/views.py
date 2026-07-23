"""Minimal project-level views that don't belong to any single app yet.

The full home page (search box, popular articles, "my recent edits")
still needs the search app (Stage 8) and audit log (Stage 9); this is an
intermediate version once articles exist.
"""

from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render

from apps.articles import selectors


def home(request):
    recent_articles = selectors.get_recent_articles(limit=10)
    return render(request, "pages/home.html", {"recent_articles": recent_articles})


@login_not_required
def custom_bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)


@login_not_required
def custom_permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


@login_not_required
def custom_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


@login_not_required
def custom_server_error(request):
    return render(request, "errors/500.html", status=500)
