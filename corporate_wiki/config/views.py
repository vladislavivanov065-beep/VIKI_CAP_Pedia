"""Minimal project-level views that don't belong to any single app yet.

The real home page (search box, recent/popular articles, "my recent
edits") lands once the articles app exists; this placeholder only proves
the base template and navigation work end to end.
"""

from django.shortcuts import render


def home(request):
    return render(request, "pages/home.html")
