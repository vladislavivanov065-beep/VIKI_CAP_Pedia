from apps.assistant.services import is_assistant_enabled


def assistant_settings(request):
    """Expose the site-wide AI-assistant on/off switch to every template --
    needed both for the sidebar toggle (admin) and for disabling the
    per-question checkbox on article pages when it's off.
    """
    return {"assistant_enabled": is_assistant_enabled()}
