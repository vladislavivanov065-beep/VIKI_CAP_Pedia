from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.articles import selectors, services
from apps.articles.diffing import build_line_diff
from apps.articles.document_import import parse_uploaded_document
from apps.articles.exceptions import ArticleEditConflict, ArticleTitleConflict
from apps.articles.forms import ArticleCreateForm, ArticleEditForm, DocumentImportUploadForm
from apps.articles.markdown_ext import extract_toc_html
from apps.articles.models import Article, ArticleRedirect, ArticleRevision, Category, Tag
from apps.articles.similarity import find_similar_articles
from apps.attachments.exceptions import InvalidAttachmentError


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
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
            except ArticleTitleConflict as exc:
                form.add_error("title", str(exc))
            else:
                services.set_article_taxonomy(
                    article_id=article.pk,
                    category_names=form.cleaned_data["categories"],
                    tag_names=form.cleaned_data["tags"],
                )
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
    similar_articles = find_similar_articles(article, limit=3) if not article.is_archived else []

    return render(
        request,
        "articles/detail.html",
        {
            "article": article,
            "revision": revision,
            "toc_html": toc_html,
            "show_source": request.GET.get("view") == "source",
            "similar_articles": similar_articles,
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
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
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
                services.set_article_taxonomy(
                    article_id=article.pk,
                    category_names=form.cleaned_data["categories"],
                    tag_names=form.cleaned_data["tags"],
                )
                messages.success(request, "Изменения сохранены.")
                return redirect("articles:detail", slug=article.slug)
    else:
        form = ArticleEditForm(
            initial={
                "content_source": revision.content_source if revision else "",
                "base_revision_id": article.current_revision_id,
                "article_version": article.version,
                "categories": ", ".join(category.name for category in article.categories.all()),
                "tags": ", ".join(tag.name for tag in article.tags.all()),
            }
        )

    return render(
        request,
        "articles/edit.html",
        {"article": article, "form": form, "conflict": False, "revision": revision},
    )


def article_link_suggestions(request):
    """Titles of existing articles, for the editor's wiki-link hints.

    ``exclude`` skips the article currently being edited so it doesn't
    suggest linking a page to itself.
    """
    articles = (
        Article.objects.filter(is_archived=False)
        .exclude(slug=request.GET.get("exclude", ""))
        .order_by("title")
        .values("id", "title", "slug")
    )
    return JsonResponse({"articles": [{**a, "id": str(a["id"])} for a in articles]})


def article_sidebar_list(request):
    """Backs the sidebar's scrollable quick-browse/quick-search widget."""
    articles = selectors.find_articles_for_sidebar_list(request.GET.get("q", ""))
    return JsonResponse({"articles": [{"title": a.title, "slug": a.slug} for a in articles]})


def article_history(request, slug: str):
    article = get_object_or_404(Article, slug=slug)
    revisions = list(selectors.get_article_history(article))  # newest first

    entries = []
    for index, revision in enumerate(revisions):
        size = len(revision.content_source)
        older_revision = revisions[index + 1] if index + 1 < len(revisions) else None
        size_diff = size - len(older_revision.content_source) if older_revision else size
        entries.append({"revision": revision, "size": size, "size_diff": size_diff})

    paginator = Paginator(entries, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "articles/history.html", {"article": article, "page_obj": page_obj})


def article_revision_detail(request, slug: str, revision_number: int):
    article = get_object_or_404(Article, slug=slug)
    revision = get_object_or_404(ArticleRevision, article=article, revision_number=revision_number)
    is_current = article.current_revision_id == revision.id
    toc_html = extract_toc_html(revision.content_html)

    numbers = list(
        article.revisions.order_by("revision_number").values_list("revision_number", flat=True)
    )
    position = numbers.index(revision_number)
    previous_number = numbers[position - 1] if position > 0 else None
    next_number = numbers[position + 1] if position + 1 < len(numbers) else None

    return render(
        request,
        "articles/revision_detail.html",
        {
            "article": article,
            "revision": revision,
            "is_current": is_current,
            "toc_html": toc_html,
            "previous_number": previous_number,
            "next_number": next_number,
        },
    )


def article_compare(request, slug: str):
    article = get_object_or_404(Article, slug=slug)

    try:
        from_number = int(request.GET.get("from", ""))
        to_number = int(request.GET.get("to", ""))
    except (TypeError, ValueError):
        raise Http404("Укажите обе версии для сравнения (from и to).") from None

    from_revision = get_object_or_404(ArticleRevision, article=article, revision_number=from_number)
    to_revision = get_object_or_404(ArticleRevision, article=article, revision_number=to_number)

    if from_revision.revision_number > to_revision.revision_number:
        from_revision, to_revision = to_revision, from_revision

    diff_lines = build_line_diff(from_revision.content_source, to_revision.content_source)
    view_mode = "unified" if request.GET.get("view") == "unified" else "split"

    return render(
        request,
        "articles/compare.html",
        {
            "article": article,
            "from_revision": from_revision,
            "to_revision": to_revision,
            "diff_lines": diff_lines,
            "view_mode": view_mode,
        },
    )


@require_POST
def article_restore(request, slug: str, revision_number: int):
    article = get_object_or_404(Article, slug=slug)

    try:
        article_version = int(request.POST.get("article_version", ""))
    except (TypeError, ValueError):
        raise Http404("Некорректная версия статьи.") from None

    try:
        services.restore_revision(
            article_id=article.pk,
            revision_number=revision_number,
            base_revision_id=request.POST.get("base_revision_id") or None,
            article_version=article_version,
            actor=request.user,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except ArticleEditConflict:
        messages.error(
            request, "Статья изменилась с момента открытия этой страницы. Попробуйте ещё раз."
        )
        return redirect("articles:revision_detail", slug=slug, revision_number=revision_number)

    messages.success(request, f"Версия №{revision_number} восстановлена.")
    return redirect("articles:detail", slug=article.slug)


@require_POST
def article_archive(request, slug: str):
    # Archiving is an administrator-only action (section 3.2) — physical
    # deletion of an article is never allowed through the UI at all.
    if not request.user.is_staff:
        raise PermissionDenied

    article = get_object_or_404(Article, slug=slug, is_archived=False)
    services.archive_article(
        article_id=article.pk,
        actor=request.user,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    messages.success(request, "Статья перенесена в архив.")
    return redirect("articles:detail", slug=article.slug)


@require_POST
def article_unarchive(request, slug: str):
    if not request.user.is_staff:
        raise PermissionDenied

    article = get_object_or_404(Article, slug=slug, is_archived=True)
    try:
        services.restore_article(
            article_id=article.pk,
            actor=request.user,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except ArticleTitleConflict as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Статья восстановлена из архива.")
    return redirect("articles:detail", slug=article.slug)


# Admin document-import wizard (section: upload -> heuristic split -> review).
# The parsed blocks live in the session between the upload and review steps —
# nothing is written to the database until the administrator approves a block.
_IMPORT_SESSION_KEY = "document_import_blocks"
_IMPORT_FILENAME_SESSION_KEY = "document_import_filename"


def document_import_upload(request):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method == "POST":
        form = DocumentImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["document"]
            try:
                blocks = parse_uploaded_document(file_obj=uploaded, original_filename=uploaded.name)
            except InvalidAttachmentError as exc:
                form.add_error("document", str(exc))
            else:
                request.session[_IMPORT_SESSION_KEY] = {
                    str(index): {"title": block.title, "content": block.content}
                    for index, block in enumerate(blocks)
                }
                request.session[_IMPORT_FILENAME_SESSION_KEY] = uploaded.name
                return redirect("articles:import_review")
    else:
        form = DocumentImportUploadForm()

    return render(request, "articles/import_upload.html", {"form": form})


def document_import_review(request):
    if not request.user.is_staff:
        raise PermissionDenied

    blocks = request.session.get(_IMPORT_SESSION_KEY) or {}
    entries = [
        {"id": block_id, "title": block["title"], "content": block["content"]}
        for block_id, block in sorted(blocks.items(), key=lambda item: int(item[0]))
    ]

    return render(
        request,
        "articles/import_review.html",
        {
            "entries": entries,
            "filename": request.session.get(_IMPORT_FILENAME_SESSION_KEY, ""),
        },
    )


@require_POST
def document_import_process_block(request, block_id: str):
    if not request.user.is_staff:
        raise PermissionDenied

    blocks = request.session.get(_IMPORT_SESSION_KEY) or {}
    block = blocks.get(block_id)
    if block is None:
        raise Http404("Блок не найден или уже обработан.")

    action = request.POST.get("action")
    title = request.POST.get("title", block["title"]).strip()
    content = request.POST.get("content", block["content"])

    if action == "skip":
        del blocks[block_id]
        request.session[_IMPORT_SESSION_KEY] = blocks
        request.session.modified = True
        messages.info(request, f"Блок «{block['title']}» пропущен.")
        return redirect("articles:import_review")

    if action in ("add", "edit_add"):
        try:
            article = services.create_article(
                title=title or block["title"],
                content_source=content,
                created_by=request.user,
                edit_summary="Импорт из документа",
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ArticleTitleConflict as exc:
            messages.error(request, str(exc))
            blocks[block_id] = {"title": title, "content": content}
            request.session[_IMPORT_SESSION_KEY] = blocks
            request.session.modified = True
            return redirect("articles:import_review")
        else:
            del blocks[block_id]
            request.session[_IMPORT_SESSION_KEY] = blocks
            request.session.modified = True
            messages.success(request, f"Статья «{article.title}» добавлена.")
            return redirect("articles:import_review")

    raise Http404("Неизвестное действие.")


def category_list(request):
    top_level = (
        Category.objects.filter(parent__isnull=True).prefetch_related("children").order_by("name")
    )
    return render(request, "articles/category_list.html", {"categories": top_level})


def category_detail(request, slug: str):
    category = get_object_or_404(Category, slug=slug)
    articles = category.articles.filter(is_archived=False).order_by("title")
    subcategories = category.children.order_by("name")
    return render(
        request,
        "articles/category_detail.html",
        {"category": category, "articles": articles, "subcategories": subcategories},
    )


def tag_detail(request, slug: str):
    tag = get_object_or_404(Tag, slug=slug)
    articles = tag.articles.filter(is_archived=False).order_by("title")
    return render(request, "articles/tag_detail.html", {"tag": tag, "articles": articles})
