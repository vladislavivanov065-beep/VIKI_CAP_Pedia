from django.contrib import admin
from django.urls import include, path

from config.health import liveness, readiness
from config.views import home

urlpatterns = [
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("articles/", include("apps.articles.urls")),
    path("admin/", admin.site.urls),
    path("health/live/", liveness, name="health-live"),
    path("health/ready/", readiness, name="health-ready"),
]

handler400 = "config.views.custom_bad_request"
handler403 = "config.views.custom_permission_denied"
handler404 = "config.views.custom_not_found"
handler500 = "config.views.custom_server_error"
