from django.conf import settings


def site_settings(request):
    """Expose the configurable site name/URL to every template."""
    return {
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
    }
