from __future__ import annotations

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.articles import selectors, services
from apps.articles.exceptions import ArticleEditConflict, ArticleTitleConflict
from apps.articles.forms import ArticleCreateForm, ArticleEditForm, ArticlePreviewForm
from apps.articles.markdown_ext import extract_toc_html, render_article_content
from apps.articles.models import Article, ArticleRedirect


def article_create(request):
    initial = {"title": request.GET.get("title", "")}

    if request.method == "POST":
        form = ArticleCreateForm(request.POST)
        if form.is_valid():
            try:
                article = services.create_article(
                    title=form.cleaned_data["title"],
                    content_source=form.cleaned_data["content_source"],
                    edit_summary=form.cleaned_data["edit_summary"],
                    created_by=request.user,
                )
            except ArticleTitleConflict as exc:
                form.add_error("title", str(exc))
            else:
                messages.success(request, "Статья создана.")
                return redirect("articles:detail", slug=article.slug)
    else:
        form = ArticleCreateForm(initial=initial)

    return render(request, "articles/create.html", {"form": form})


def _resolve_article_or_redirect(slug: str, *, include_archived: bool = True):
    """Look the slug up as a live article, then fall back to a redirect
    entry left behind by a rename (section 4.6). Returns either an Article
    or an HttpResponse (redirect) to send straight back to the caller.
    """
    try:
        return selectors.get_article_by_slug(slug, include_archived=include_archived), None
    except Article.DoesNotExist:
        pass

    redirect_entry = ArticleRedirect.objects.filter(old_slug=slug).select_related("article").first()
    if redirect_entry is not None:
        return None, redirect("articles:detail", slug=redirect_entry.article.slug, permanent=True)

    return None, None


def article_detail(request, slug: str):
    article, redirect_response = _resolve_article_or_redirect(slug)
    if redirect_response is not None:
        return redirect_response
    if article is None:
        raise Http404("Статья не найдена.")

    revision = article.current_revision
    toc_html = extract_toc_html(revision.content_html) if revision else ""

    return render(
        request,
        "articles/detail.html",
        {
            "article": article,
            "revision": revision,
            "toc_html": toc_html,
        },
    )


def article_edit(request, slug: str):
    article = get_object_or_404(Article, slug=slug, is_archived=False)
    revision = article.current_revision

    if request.method == "POST":
        form = ArticleEditForm(request.POST)
        if form.is_valid():
            try:
                services.update_article(
                    article_id=article.pk,
                    base_revision_id=form.cleaned_data["base_revision_id"] or None,
                    article_version=form.cleaned_data["article_version"],
                    content_source=form.cleaned_data["content_source"],
                    edit_summary=form.cleaned_data["edit_summary"],
                    edited_by=request.user,
                )
            except ArticleEditConflict as exc:
                messages.error(
                    request,
                    "Статью успел изменить другой пользователь. Ваш текст сохранён ниже — "
                    "сравните его с текущей версией и сохраните ещё раз, если всё в порядке.",
                )
                form = ArticleEditForm(
                    initial={
                        "content_source": form.cleaned_data["content_source"],
                        "edit_summary": form.cleaned_data["edit_summary"],
                        "base_revision_id": exc.current_article.current_revision_id,
                        "article_version": exc.current_article.version,
                    }
                )
                return render(
                    request,
                    "articles/edit.html",
                    {
                        "article": article,
                        "form": form,
                        "conflict": True,
                        "current_revision": exc.current_revision,
                    },
                )
            else:
                messages.success(request, "Изменения сохранены.")
                return redirect("articles:detail", slug=article.slug)
    else:
        form = ArticleEditForm(
            initial={
                "content_source": revision.content_source if revision else "",
                "base_revision_id": article.current_revision_id,
                "article_version": article.version,
            }
        )

    return render(
        request, "articles/edit.html", {"article": article, "form": form, "conflict": False}
    )


@require_POST
def article_preview(request):
    form = ArticlePreviewForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"content_html": "", "toc_html": ""})

    content_html, toc_html = render_article_content(form.cleaned_data["content_source"])
    return JsonResponse({"content_html": content_html, "toc_html": toc_html})
