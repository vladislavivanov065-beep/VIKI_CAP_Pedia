import factory
from factory.django import DjangoModelFactory

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import Article


class ArticleFactory(DjangoModelFactory):
    class Meta:
        model = Article

    title = factory.Sequence(lambda n: f"Тестовая статья {n}")
    content_source = "Содержимое статьи."
    created_by = factory.SubFactory(UserFactory)

    @classmethod
    def _create(cls, model_class, *, title, content_source, created_by, **kwargs):
        return services.create_article(
            title=title,
            content_source=content_source,
            created_by=created_by,
            **kwargs,
        )
