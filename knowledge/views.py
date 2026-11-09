from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from knowledge.documents import create_document, reject_oversized_request
from knowledge.models import Document, KnowledgeBase
from knowledge.serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    KnowledgeBaseSerializer,
)
from tenants.scoping import TenantScopedViewMixin


class KnowledgeBaseViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_knowledge_base(self):
        return get_object_or_404(
            KnowledgeBase.objects.for_tenant(self.request.user.tenant),
            pk=self.kwargs["knowledge_base_id"],
        )

    def get_queryset(self):
        return Document.objects.for_tenant(self.request.user.tenant).filter(
            knowledge_base=self.get_knowledge_base()
        )

    @extend_schema(request=DocumentUploadSerializer, responses={202: DocumentSerializer})
    def create(self, request, knowledge_base_id=None):
        knowledge_base = self.get_knowledge_base()
        reject_oversized_request(request)
        payload = DocumentUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        document = create_document(
            knowledge_base, payload.validated_data["file"], payload.validated_data.get("title")
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)
