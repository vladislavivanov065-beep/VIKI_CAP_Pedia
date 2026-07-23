"""Minimal project-level views that don't belong to any single app yet.

The real home page (search box, recent/popular articles, "my recent
edits") lands once the articles app exists; this placeholder only proves
the base template and navigation work end to end.
"""

from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render


def home(request):
    return render(request, "pages/home.html")


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
