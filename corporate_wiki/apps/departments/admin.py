from django.contrib import admin

from apps.departments.models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
