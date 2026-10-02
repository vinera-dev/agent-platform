from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from config.health import health


def public(view, **initkwargs):
    return view.as_view(
        permission_classes=[AllowAny],
        authentication_classes=[],
        throttle_classes=[],
        **initkwargs,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    path("v1/schema", public(SpectacularAPIView), name="schema"),
    path("v1/docs", public(SpectacularSwaggerView, url_name="schema")),
    path("v1/", include("tenants.urls")),
    path("v1/", include("agents.urls")),
]
