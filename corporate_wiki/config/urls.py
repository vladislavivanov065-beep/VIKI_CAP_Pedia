from django.contrib import admin
from django.urls import path

from config.health import liveness, readiness

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", liveness, name="health-live"),
    path("health/ready/", readiness, name="health-ready"),
]
