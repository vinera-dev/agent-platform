from django.urls import path
from rest_framework.routers import SimpleRouter

from evaluation.views import EvalCaseViewSet, EvalDatasetViewSet

router = SimpleRouter(trailing_slash=False)
router.register("eval-datasets", EvalDatasetViewSet, basename="evaldataset")

case_list = EvalCaseViewSet.as_view({"get": "list", "post": "create"})
case_detail = EvalCaseViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path("eval-datasets/<uuid:dataset_id>/cases", case_list),
    path("eval-datasets/<uuid:dataset_id>/cases/<uuid:pk>", case_detail),
    *router.urls,
]
