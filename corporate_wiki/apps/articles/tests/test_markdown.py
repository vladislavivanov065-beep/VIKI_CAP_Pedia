import re

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


def test_wikilink_to_existing_article_carries_data_article_id_for_editor_roundtrip():
    user = UserFactory()
    article = services.create_article(
        title="Отпускные правила", content_source="текст", created_by=user
    )

    html, _toc = render_article_content("[[Отпускные правила]]")
    assert f'data-wiki-article-id="{article.pk}"' in html


def test_wikilink_to_missing_article_carries_data_title_for_editor_roundtrip():
    html, _toc = render_article_content("[[Ещё не написана]]")
    assert 'data-wiki-title="Ещё не написана"' in html


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


def test_wikilink_by_uuid_carries_data_article_id_for_editor_roundtrip():
    user = UserFactory()
    article = services.create_article(title="По UUID", content_source="текст", created_by=user)

    html, _toc = render_article_content(f"[[article:{article.pk}|ссылка]]")
    assert f'data-wiki-article-id="{article.pk}"' in html


def test_wikilink_by_missing_uuid_carries_data_uuid_for_editor_roundtrip():
    html, _toc = render_article_content("[[article:00000000-0000-0000-0000-000000000000|text]]")
    assert 'data-wiki-uuid="00000000-0000-0000-0000-000000000000"' in html


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


def test_image_embed_renders_figure_with_src():
    from io import BytesIO

    from apps.images import services
    from apps.images.tests.factories import make_image_bytes

    user = UserFactory()
    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"![[image:{image.pk}]]")
    assert f'src="/images/{image.pk}/"' in html
    assert f'data-image-id="{image.pk}"' in html
    assert "<figure>" in html


def test_image_embed_with_caption():
    from io import BytesIO

    from apps.images import services
    from apps.images.tests.factories import make_image_bytes

    user = UserFactory()
    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"![[image:{image.pk}|Подпись к фото]]")
    assert "<figcaption>Подпись к фото</figcaption>" in html


def test_image_embed_missing_uuid_shows_placeholder():
    html, _toc = render_article_content("![[image:00000000-0000-0000-0000-000000000000]]")
    assert "изображение не найдено" in html
    assert "wiki-link-missing" in html


def test_image_embed_does_not_get_treated_as_wikilink():
    html, _toc = render_article_content("![[image:not-a-real-uuid]]")
    assert "<img" not in html
    assert "изображение не найдено" in html


def test_image_embed_with_align_and_size_options():
    from io import BytesIO

    from apps.images import services
    from apps.images.tests.factories import make_image_bytes

    user = UserFactory()
    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"![[image:{image.pk}|Подпись|align=left;size=medium]]")
    assert 'class="wiki-image--align-left wiki-image--size-medium"' in html
    assert "<figcaption>Подпись</figcaption>" in html


def test_image_embed_with_options_but_no_caption():
    from io import BytesIO

    from apps.images import services
    from apps.images.tests.factories import make_image_bytes

    user = UserFactory()
    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"![[image:{image.pk}||align=right]]")
    assert 'class="wiki-image--align-right"' in html
    assert "<figcaption>" not in html


def test_image_embed_ignores_unknown_options():
    from io import BytesIO

    from apps.images import services
    from apps.images.tests.factories import make_image_bytes

    user = UserFactory()
    image = services.upload_article_image(
        file_obj=BytesIO(make_image_bytes()),
        original_filename="a.png",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"![[image:{image.pk}|Подпись|align=diagonal]]")
    assert "<figure>" in html


def test_attachment_embed_renders_download_link():
    from io import BytesIO

    from apps.attachments import services
    from apps.attachments.tests.factories import make_txt_bytes

    user = UserFactory()
    attachment = services.upload_attachment(
        file_obj=BytesIO(make_txt_bytes()),
        original_filename="отчёт.txt",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"[[attachment:{attachment.pk}]]")
    assert f'href="/attachments/{attachment.pk}/download/"' in html
    assert f'data-attachment-id="{attachment.pk}"' in html
    assert 'class="attachment-link"' in html
    assert "отчёт.txt" in html


def test_attachment_embed_with_custom_display_text():
    from io import BytesIO

    from apps.attachments import services
    from apps.attachments.tests.factories import make_txt_bytes

    user = UserFactory()
    attachment = services.upload_attachment(
        file_obj=BytesIO(make_txt_bytes()),
        original_filename="отчёт.txt",
        uploaded_by=user,
    )

    html, _toc = render_article_content(f"[[attachment:{attachment.pk}|Скачать отчёт]]")
    assert "Скачать отчёт" in html
    # The real filename still appears in `download=""`, but the visible
    # link text is the custom display text, not the filename.
    anchor_text = re.search(r"<a[^>]*>([^<]*)</a>", html).group(1)
    assert anchor_text == "\U0001f4ce Скачать отчёт"


def test_attachment_embed_missing_shows_placeholder():
    html, _toc = render_article_content("[[attachment:00000000-0000-0000-0000-000000000000]]")
    assert "вложение не найдено" in html
    assert "wiki-link-missing" in html


def test_attachment_embed_does_not_collide_with_wikilink_title_syntax():
    # A literal [[attachment:...]] with a non-UUID target must still be
    # treated as an attachment reference (and reported missing), not
    # accidentally parsed as a wikilink titled "attachment:not-a-uuid".
    html, _toc = render_article_content("[[attachment:not-a-uuid]]")
    assert "вложение не найдено" in html


def test_text_color_renders_as_span_with_style():
    html, _toc = render_article_content("{color:#ff0000}красный{/color}")
    assert '<span style="color:#ff0000">красный</span>' in html


def test_text_background_renders_as_span_with_style():
    html, _toc = render_article_content("{bg:#ffff00}выделено{/bg}")
    assert '<span style="background-color:#ffff00">выделено</span>' in html


def test_text_color_and_background_can_nest():
    html, _toc = render_article_content("{bg:#00ff00}{color:#0000ff}вложено{/color}{/bg}")
    assert '<span style="background-color:#00ff00">' in html
    assert '<span style="color:#0000ff">вложено</span>' in html


def test_text_color_composes_with_other_inline_formatting():
    html, _toc = render_article_content("{color:#ff0000}**жирный красный**{/color}")
    assert "<strong>жирный красный</strong>" in html
    assert 'style="color:#ff0000"' in html


def test_text_color_ignores_invalid_hex_value():
    html, _toc = render_article_content("{color:red}текст{/color}")
    assert "style=" not in html
    assert "{color:red}текст{/color}" in html


def test_hand_typed_style_attribute_is_restricted_to_color_properties():
    # Even raw HTML in the source (which Markdown passes through verbatim
    # before nh3 sanitizes it) can never carry more than a colour value --
    # filter_style_properties strips everything else regardless of where
    # the style attribute came from.
    html, _toc = render_article_content(
        '<span style="color: red; position: fixed; behavior: url(evil.htc)">x</span>'
    )
    assert "position" not in html
    assert "behavior" not in html
    assert "color: red" in html or "color:red" in html
