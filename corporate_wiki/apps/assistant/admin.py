from django.contrib import admin

from apps.assistant.models import AssistantSettings


@admin.register(AssistantSettings)
class AssistantSettingsAdmin(admin.ModelAdmin):
    list_display = ["is_enabled", "updated_by", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        # Singleton (see AssistantSettings.get_solo) -- never more than one row.
        return not AssistantSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
