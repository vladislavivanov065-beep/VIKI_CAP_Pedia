import pytest
from django.db import IntegrityError, transaction

from apps.departments.models import Department

pytestmark = pytest.mark.django_db


def test_str_returns_the_name():
    department = Department.objects.create(name="HR")

    assert str(department) == "HR"


def test_name_must_be_unique():
    Department.objects.create(name="HR")

    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(name="HR")


def test_ordered_by_name():
    Department.objects.create(name="IT")
    Department.objects.create(name="HR")

    names = list(Department.objects.values_list("name", flat=True))

    assert names == ["HR", "IT"]
