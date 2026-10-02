from rest_framework.routers import SimpleRouter

from agents.views import AgentViewSet

router = SimpleRouter(trailing_slash=False)
router.register("agents", AgentViewSet, basename="agent")

urlpatterns = router.urls
