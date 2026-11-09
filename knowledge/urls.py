from django.urls import path
from rest_framework.routers import SimpleRouter

from knowledge.views import DocumentViewSet, KnowledgeBaseViewSet, SearchViewSet

router = SimpleRouter(trailing_slash=False)
router.register("knowledge-bases", KnowledgeBaseViewSet, basename="knowledgebase")

document_list = DocumentViewSet.as_view({"get": "list", "post": "create"})
search = SearchViewSet.as_view({"post": "create"})
document_detail = DocumentViewSet.as_view({"get": "retrieve", "delete": "destroy"})

urlpatterns = [
    path("knowledge-bases/<uuid:knowledge_base_id>/documents", document_list),
    path("knowledge-bases/<uuid:knowledge_base_id>/documents/<uuid:pk>", document_detail),
    path("knowledge-bases/<uuid:knowledge_base_id>/search", search),
    *router.urls,
]
