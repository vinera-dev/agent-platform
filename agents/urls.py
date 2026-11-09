from django.urls import path
from rest_framework.routers import SimpleRouter

from agents.views import AgentRunViewSet, AgentVersionViewSet, AgentViewSet, RunViewSet, UsageView

router = SimpleRouter(trailing_slash=False)
router.register("agents", AgentViewSet, basename="agent")
router.register("runs", RunViewSet, basename="run")

version_list = AgentVersionViewSet.as_view({"get": "list", "post": "create"})
version_detail = AgentVersionViewSet.as_view({"get": "retrieve"})
version_publish = AgentVersionViewSet.as_view({"post": "publish"})
version_archive = AgentVersionViewSet.as_view({"post": "archive"})

run_create = AgentRunViewSet.as_view({"post": "create"})

urlpatterns = [
    path("usage", UsageView.as_view()),
    path("agents/<uuid:agent_id>/runs", run_create),
    path("agents/<uuid:agent_id>/versions", version_list),
    path("agents/<uuid:agent_id>/versions/<uuid:pk>", version_detail),
    path("agents/<uuid:agent_id>/versions/<uuid:pk>/publish", version_publish),
    path("agents/<uuid:agent_id>/versions/<uuid:pk>/archive", version_archive),
    *router.urls,
]
