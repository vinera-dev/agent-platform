from django.contrib import admin
from django.urls import include, path

from config.health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    path("v1/", include("tenants.urls")),
    path("v1/", include("agents.urls")),
]
