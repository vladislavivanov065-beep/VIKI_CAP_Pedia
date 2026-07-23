import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.markdown_ext import extract_toc_html, render_article_content

pytestmark = pytest.mark.django_db


def test_basic_formatting_renders_expected_tags():
    html, _toc = render_article_content("**bold** *italic* ~~strike~~ `code`")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<del>strike</del>" in html
    assert "<code>code</code>" in html


def test_table_and_fenced_code_render():
    source = "| A | B |\n| - | - |\n| 1 | 2 |\n\n```\nprint(1)\n```\n"
    html, _toc = render_article_content(source)
    assert "<table>" in html
    assert "<pre>" in html and "print(1)" in html


def test_headings_get_ids_and_toc_is_built_with_cyrillic_slugs():
    source = "## Первый раздел\ntext\n### Подраздел\ntext\n## Второй раздел\ntext"
    html, toc = render_article_content(source)
    assert 'id="первый-раздел"' in html
    assert 'href="#первый-раздел"' in toc
    assert 'href="#подраздел"' in toc


def test_h1_and_h4_are_excluded_from_toc_but_still_render():
    source = "# H1\ntext\n#### H4\ntext\n## H2\ntext"
    html, toc = render_article_content(source)
    assert "<h1" in html
    assert "<h4" in html
    assert "H1" not in toc
    assert "H4" not in toc
    assert "H2" in toc


def test_script_tag_is_stripped():
    html, _toc = render_article_content("<script>alert('xss')</script>Text")
    assert "<script" not in html
    assert "alert" not in html
    assert "Text" in html


def test_javascript_url_scheme_is_stripped():
    html, _toc = render_article_content('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in html


def test_onclick_and_style_attributes_are_stripped():
    html, _toc = render_article_content('<p onclick="evil()" style="color:red">hi</p>')
    assert "onclick" not in html
    assert "style" not in html


def test_iframe_is_stripped():
    html, _toc = render_article_content('<iframe src="https://evil.example"></iframe>Text')
    assert "<iframe" not in html
    assert "Text" in html


def test_external_link_gets_rel_and_target_and_class():
    html, _toc = render_article_content("[site](https://example.com/page)")
    assert 'class="external-link"' in html
    assert 'rel="noopener noreferrer"' in html
    assert 'target="_blank"' in html


def test_relative_link_is_not_marked_external():
    html, _toc = render_article_content("[home](/articles/foo/)")
    assert "external-link" not in html


def test_wikilink_to_existing_article_is_blue():
    user = UserFactory()
    services.create_article(title="Отпускные правила", content_source="текст", created_by=user)

    html, _toc = render_article_content("См. [[Отпускные правила]] для подробностей.")
    assert 'class="wiki-link"' in html
    assert 'href="/articles/otpusknye-pravila/"' in html or "href=" in html


def test_wikilink_case_insensitive_match():
    user = UserFactory()
    services.create_article(title="Отпускные правила", content_source="текст", created_by=user)

    html, _toc = render_article_content("[[отпускные ПРАВИЛА]]")
    assert 'class="wiki-link"' in html


def test_wikilink_with_custom_display_text():
    user = UserFactory()
    services.create_article(title="Правила", content_source="текст", created_by=user)

    html, _toc = render_article_content("[[Правила|наши правила]]")
    assert ">наши правила<" in html


def test_wikilink_to_missing_article_is_red_and_links_to_create():
    html, _toc = render_article_content("[[Несуществующая статья]]")
    assert 'class="wiki-link-missing"' in html
    assert "/articles/create/?title=" in html


def test_wikilink_to_archived_article_has_distinct_indicator():
    user = UserFactory()
    article = services.create_article(title="Архивная", content_source="текст", created_by=user)
    services.archive_article(article_id=article.pk, actor=user)

    html, _toc = render_article_content("[[Архивная]]")
    assert 'class="wiki-link-archived"' in html


def test_wikilink_by_uuid():
    user = UserFactory()
    article = services.create_article(title="По UUID", content_source="текст", created_by=user)

    html, _toc = render_article_content(f"[[article:{article.pk}|ссылка]]")
    assert 'class="wiki-link"' in html
    assert ">ссылка<" in html


def test_wikilink_by_invalid_uuid_is_missing():
    html, _toc = render_article_content("[[article:not-a-uuid|text]]")
    assert "wiki-link-missing" in html


def test_extract_toc_html_matches_render_time_toc():
    source = "## Раздел один\ntext\n### Под раздел\ntext\n## Раздел два\ntext"
    html, toc = render_article_content(source)
    rebuilt_toc = extract_toc_html(html)
    assert 'href="#раздел-один"' in rebuilt_toc
    assert 'href="#под-раздел"' in rebuilt_toc
    assert 'href="#раздел-два"' in rebuilt_toc
    assert toc.count("<li>") == rebuilt_toc.count("<li>")


def test_extract_toc_html_empty_when_no_headings():
    html, _toc = render_article_content("Просто текст без заголовков.")
    assert extract_toc_html(html) == ""
