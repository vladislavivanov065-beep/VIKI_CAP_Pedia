import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import User

DEFAULT_TEST_PASSWORD = "StrongPassw0rd!23"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True
    is_staff = False
    is_superuser = False
    must_change_password = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", DEFAULT_TEST_PASSWORD)
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)
