from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.articles import visibility
from apps.articles.models import Article
from apps.comments import services
from apps.comments.forms import CommentForm
from apps.comments.models import Comment


@require_POST
def comment_create(request, slug: str):
    article = get_object_or_404(Article, slug=slug, is_archived=False)
    if not visibility.article_is_visible(article, request.user):
        raise Http404("Статья не найдена.")
    form = CommentForm(request.POST)

    parent = None
    parent_id = request.POST.get("parent_id", "").strip()
    if parent_id:
        # Not trusting the hidden field as-is: a parent_id has to name a
        # real comment on *this* article, otherwise a reply could be
        # smuggled onto a different article's thread.
        parent = Comment.objects.filter(pk=parent_id, article=article).first()
        if parent is None:
            messages.error(request, "Комментарий, на который вы отвечали, не найден.")
            return redirect("articles:detail", slug=article.slug)

    detail_url = reverse("articles:detail", args=[article.slug])

    if not form.is_valid():
        errors = [str(error) for error in form.errors.get("text", [])]
        messages.error(request, " ".join(errors) or "Не удалось сохранить комментарий.")
        return redirect(detail_url)

    comment = services.create_comment(
        article=article, author=request.user, text=form.cleaned_data["text"], parent=parent
    )
    return redirect(f"{detail_url}#comment-{comment.pk}")
