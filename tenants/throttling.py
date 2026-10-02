from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

from tenants.authentication import TenantPrincipal


class TenantRateThrottle(SimpleRateThrottle):
    scope = "tenant"

    def get_rate(self):
        return settings.TENANT_RATE_LIMIT

    def get_cache_key(self, request, view):
        principal = request.user
        if not isinstance(principal, TenantPrincipal):
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(principal.tenant.pk)}
