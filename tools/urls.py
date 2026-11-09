from rest_framework.routers import SimpleRouter

from tools.views import ToolViewSet

router = SimpleRouter(trailing_slash=False)
router.register("tools", ToolViewSet, basename="tool")

urlpatterns = router.urls
