"""Health check views used by the container orchestrator.

Kept outside of any app because they must work even before the
application's own apps (accounts, articles, ...) are wired up.
"""

from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse


@login_not_required
def liveness(request):
    """Confirm the process is up and able to answer requests."""
    return JsonResponse({"status": "ok"})


@login_not_required
def readiness(request):
    """Confirm the application can actually talk to its SQLite database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError:
        return JsonResponse({"status": "error", "detail": "database unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
