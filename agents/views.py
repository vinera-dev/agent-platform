from rest_framework import viewsets

from agents.models import Agent
from agents.serializers import AgentSerializer
from tenants.scoping import TenantScopedViewMixin


class AgentViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
