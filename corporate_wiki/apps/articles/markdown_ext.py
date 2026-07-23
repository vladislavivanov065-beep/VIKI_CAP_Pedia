"""Markdown -> sanitized HTML pipeline (section 5).

Wiki-link syntax ([[Title]], [[Title|text]], [[article:UUID|text]]) is
implemented as inline patterns so it composes correctly with the rest of
Markdown's parsing instead of a naive text substitution pass. Everything
produced here still goes through nh3 before it's trusted — the renderer
never returns unsanitized HTML.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as etree
from urllib.parse import quote
from xml.sax.saxutils import escape

import markdown
import nh3
from django.conf import settings
from django.core.exceptions import ValidationError
from markdown.extensions import Extension
from markdown.extensions.toc import slugify_unicode
from markdown.inlinepatterns import InlineProcessor, SimpleTagInlineProcessor
from markdown.treeprocessors import Treeprocessor

WIKILINK_UUID_RE = r"\[\[article:([^\|\]]+)(?:\|([^\]]+))?\]\]"
WIKILINK_TITLE_RE = r"\[\[(?!article:)([^\|\]]+)(?:\|([^\]]+))?\]\]"
STRIKETHROUGH_RE = r"(~~)(.*?)~~"

_INTERNAL_LINK_CLASSES = {"wiki-link", "wiki-link-missing", "wiki-link-archived"}

SANITIZE_TAGS = {
    "p",
    "br",
    "hr",
    "strong",
    "em",
    "del",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "img",
}
SANITIZE_ATTRIBUTES = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title"},
    **{f"h{level}": {"id"} for level in range(1, 7)},
}
SANITIZE_CLASSES = {"a": _INTERNAL_LINK_CLASSES | {"external-link"}}
SANITIZE_URL_SCHEMES = {"http", "https", "mailto"}


def _article_href(article) -> str:
    return f"/articles/{article.slug}/"


def _missing_article_href(title: str) -> str:
    return f"/articles/create/?title={quote(title)}"


class WikiLinkByUuidInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        from apps.articles.models import Article

        raw_uuid, display = m.group(1), (m.group(2) or m.group(1)).strip()
        anchor = etree.Element("a")
        anchor.text = display
        try:
            article = Article.objects.get(pk=raw_uuid)
        except (Article.DoesNotExist, ValueError, ValidationError):
            anchor.set("class", "wiki-link-missing")
            return anchor, m.start(0), m.end(0)

        anchor.set("href", _article_href(article))
        if article.is_archived:
            anchor.set("class", "wiki-link-archived")
            anchor.set("title", "Статья архивирована")
        else:
            anchor.set("class", "wiki-link")
        return anchor, m.start(0), m.end(0)


class WikiLinkByTitleInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        from apps.articles.models import Article

        title = m.group(1).strip()
        display = (m.group(2) or title).strip()
        anchor = etree.Element("a")
        anchor.text = display

        try:
            article = Article.objects.get(title_normalized=title.lower())
        except Article.DoesNotExist:
            anchor.set("href", _missing_article_href(title))
            anchor.set("class", "wiki-link-missing")
            return anchor, m.start(0), m.end(0)

        anchor.set("href", _article_href(article))
        if article.is_archived:
            anchor.set("class", "wiki-link-archived")
            anchor.set("title", "Статья архивирована")
        else:
            anchor.set("class", "wiki-link")
        return anchor, m.start(0), m.end(0)


class ExternalLinkTreeprocessor(Treeprocessor):
    """Marks plain ``[text](url)`` links to other domains as external."""

    def run(self, root):
        site_url = settings.SITE_URL
        for anchor in root.iter("a"):
            classes = set((anchor.get("class") or "").split())
            if classes & _INTERNAL_LINK_CLASSES:
                continue
            href = anchor.get("href") or ""
            if not (href.startswith("http://") or href.startswith("https://")):
                continue
            if href.startswith(site_url):
                continue
            classes.add("external-link")
            anchor.set("class", " ".join(sorted(classes)))
            if getattr(settings, "EXTERNAL_LINKS_NEW_TAB", True):
                anchor.set("target", "_blank")


class CorporateWikiExtension(Extension):
    """Wiki-links, strikethrough, and external-link marking in one place."""

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            WikiLinkByUuidInlineProcessor(WIKILINK_UUID_RE, md), "wikilink_uuid", 176
        )
        md.inlinePatterns.register(
            WikiLinkByTitleInlineProcessor(WIKILINK_TITLE_RE, md), "wikilink_title", 175
        )
        md.inlinePatterns.register(
            SimpleTagInlineProcessor(STRIKETHROUGH_RE, "del"), "strikethrough", 170
        )
        md.treeprocessors.register(ExternalLinkTreeprocessor(md), "external_links", 4)


def _build_toc_html(tokens: list[dict]) -> str:
    if not tokens:
        return ""
    parts = ["<ul>"]
    for token in tokens:
        parts.append(f'<li><a href="#{token["id"]}">{escape(token["name"])}</a>')
        parts.append(_build_toc_html(token.get("children") or []))
        parts.append("</li>")
    parts.append("</ul>")
    return "".join(parts)


def render_article_content(source: str) -> tuple[str, str]:
    """Convert Markdown source into sanitized HTML and a TOC fragment.

    Returns ``(content_html, toc_html)``; both are already sanitized and
    safe to mark as safe/render directly in a template.
    """
    md = markdown.Markdown(
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            CorporateWikiExtension(),
        ],
        extension_configs={
            "toc": {"toc_depth": "2-3", "permalink": False, "slugify": slugify_unicode},
        },
    )
    raw_html = md.convert(source or "")

    content_html = nh3.clean(
        raw_html,
        tags=SANITIZE_TAGS,
        attributes=SANITIZE_ATTRIBUTES,
        allowed_classes=SANITIZE_CLASSES,
        url_schemes=SANITIZE_URL_SCHEMES,
    )
    toc_html = nh3.clean(
        _build_toc_html(md.toc_tokens),
        tags={"ul", "li", "a"},
        attributes={"a": {"href"}},
    )
    return content_html, toc_html


_HEADING_RE = re.compile(r'<h([23])[^>]*\sid="([^"]+)"[^>]*>(.*?)</h\1>', re.DOTALL)
_INNER_TAGS_RE = re.compile(r"<[^>]+>")


def extract_toc_html(content_html: str) -> str:
    """Rebuild the TOC straight from already-rendered, already-sanitized
    revision HTML — used when displaying a saved revision, so the TOC
    always matches exactly what's on the page without re-running Markdown.
    """
    tree: list[dict] = []
    current_h2: dict | None = None
    for level_str, heading_id, inner in _HEADING_RE.findall(content_html):
        text = _INNER_TAGS_RE.sub("", inner).strip()
        node = {"id": heading_id, "name": text, "children": []}
        if level_str == "2":
            tree.append(node)
            current_h2 = node
        elif current_h2 is not None:
            current_h2["children"].append(node)
        else:
            tree.append(node)

    if not tree:
        return ""
    return nh3.clean(_build_toc_html(tree), tags={"ul", "li", "a"}, attributes={"a": {"href"}})
