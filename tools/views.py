from rest_framework import viewsets

from tenants.scoping import TenantScopedViewMixin
from tools.models import Tool
from tools.serializers import ToolCreatedSerializer, ToolSerializer


class ToolViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    queryset = Tool.objects.all()
    serializer_class = ToolSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return ToolCreatedSerializer
        return ToolSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
