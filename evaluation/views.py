from django.shortcuts import get_object_or_404
from rest_framework import viewsets

from evaluation.models import EvalCase, EvalDataset
from evaluation.serializers import EvalCaseSerializer, EvalDatasetSerializer
from tenants.scoping import TenantScopedViewMixin


class EvalDatasetViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    queryset = EvalDataset.objects.all()
    serializer_class = EvalDatasetSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class EvalCaseViewSet(viewsets.ModelViewSet):
    serializer_class = EvalCaseSerializer

    def get_dataset(self):
        return get_object_or_404(
            EvalDataset.objects.for_tenant(self.request.user.tenant),
            pk=self.kwargs["dataset_id"],
        )

    def get_queryset(self):
        return EvalCase.objects.for_tenant(self.request.user.tenant).filter(
            dataset=self.get_dataset()
        )

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant, dataset=self.get_dataset())
