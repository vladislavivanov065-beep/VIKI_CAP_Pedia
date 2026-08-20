import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services, visibility
from apps.articles.models import Article
from apps.departments.models import Department

pytestmark = pytest.mark.django_db


def _article(title="Статья"):
    admin = UserFactory()
    return services.create_article(title=title, content_source="текст", created_by=admin)


def test_unrestricted_article_is_visible_to_anyone():
    article = _article()
    user = UserFactory()

    assert visibility.article_is_visible(article, user) is True


def test_restricted_article_is_visible_to_a_user_in_the_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    article.visible_departments.add(hr)
    user = UserFactory(department=hr)

    assert visibility.article_is_visible(article, user) is True


def test_restricted_article_is_not_visible_to_a_user_in_a_different_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)
    user = UserFactory(department=it)

    assert visibility.article_is_visible(article, user) is False


def test_restricted_article_is_not_visible_to_a_user_with_no_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    article.visible_departments.add(hr)
    user = UserFactory(department=None)

    assert visibility.article_is_visible(article, user) is False


def test_restricted_article_is_visible_to_staff_regardless_of_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)
    staff_user = UserFactory(is_staff=True, department=it)

    assert visibility.article_is_visible(article, staff_user) is True


def test_article_visible_to_any_one_of_several_departments():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr, it)
    it_user = UserFactory(department=it)

    assert visibility.article_is_visible(article, it_user) is True


def test_visible_articles_queryset_includes_unrestricted_articles():
    article = _article()
    user = UserFactory()

    assert article in visibility.visible_articles(user)


def test_visible_articles_queryset_excludes_a_restricted_article_for_a_different_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)
    it_user = UserFactory(department=it)

    assert article not in visibility.visible_articles(it_user)


def test_visible_articles_queryset_includes_a_restricted_article_for_the_matching_department():
    article = _article()
    hr = Department.objects.create(name="HR")
    article.visible_departments.add(hr)
    hr_user = UserFactory(department=hr)

    assert article in visibility.visible_articles(hr_user)


def test_visible_articles_queryset_returns_everything_for_staff():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)
    staff_user = UserFactory(is_staff=True, department=it)

    assert article in visibility.visible_articles(staff_user)


def test_visible_articles_queryset_never_duplicates_a_multi_department_article():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr, it)
    hr_user = UserFactory(department=hr)

    assert list(visibility.visible_articles(hr_user)).count(article) == 1


def test_visible_articles_queryset_narrows_an_existing_queryset():
    visible = _article(title="Видна")
    hidden = _article(title="Скрыта")
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    hidden.visible_departments.add(it)
    hr_user = UserFactory(department=hr)

    result = list(visibility.visible_articles(hr_user, Article.objects.all()))

    assert visible in result
    assert hidden not in result


def test_get_visible_article_or_404_returns_the_article_when_visible():
    article = _article()
    user = UserFactory()

    result = visibility.get_visible_article_or_404(slug=article.slug, user=user)

    assert result == article


def test_get_visible_article_or_404_404s_when_restricted_to_another_department():
    from django.http import Http404

    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)
    it_user = UserFactory(department=it)

    with pytest.raises(Http404):
        visibility.get_visible_article_or_404(slug=article.slug, user=it_user)


def test_get_visible_article_or_404_404s_for_an_unknown_slug():
    from django.http import Http404

    user = UserFactory()

    with pytest.raises(Http404):
        visibility.get_visible_article_or_404(slug="no-such-article", user=user)


def test_get_visible_article_or_404_excludes_archived_by_default():
    from django.http import Http404

    article = _article()
    admin = UserFactory()
    services.archive_article(article_id=article.pk, actor=admin)
    user = UserFactory()

    with pytest.raises(Http404):
        visibility.get_visible_article_or_404(slug=article.slug, user=user)


def test_get_visible_article_or_404_includes_archived_when_asked():
    article = _article()
    admin = UserFactory()
    services.archive_article(article_id=article.pk, actor=admin)
    user = UserFactory()

    result = visibility.get_visible_article_or_404(
        slug=article.slug, user=user, include_archived=True
    )

    assert result == article


def test_set_article_visible_departments_restricts_the_article():
    article = _article()
    hr = Department.objects.create(name="HR")

    services.set_article_visible_departments(article_id=article.pk, departments=[hr])

    assert list(article.visible_departments.all()) == [hr]


def test_set_article_visible_departments_with_none_leaves_it_unrestricted():
    article = _article()
    hr = Department.objects.create(name="HR")
    article.visible_departments.add(hr)

    services.set_article_visible_departments(article_id=article.pk, departments=[])

    assert list(article.visible_departments.all()) == []


def test_set_article_visible_departments_replaces_the_previous_selection():
    article = _article()
    hr = Department.objects.create(name="HR")
    it = Department.objects.create(name="IT")
    article.visible_departments.add(hr)

    services.set_article_visible_departments(article_id=article.pk, departments=[it])

    assert list(article.visible_departments.all()) == [it]
