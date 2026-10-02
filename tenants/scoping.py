from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantScopedViewMixin:
    def get_queryset(self):
        return super().get_queryset().for_tenant(self.request.user.tenant)
