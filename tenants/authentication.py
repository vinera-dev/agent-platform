from dataclasses import dataclass

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from tenants.models import ApiKey, Tenant

AUTH_KEYWORD = "Api-Key"
LAST_USED_REFRESH_SECONDS = 60


@dataclass(frozen=True)
class TenantPrincipal:
    tenant: Tenant
    api_key: ApiKey

    is_authenticated = True
    is_anonymous = False

    @property
    def pk(self):
        return self.tenant.pk


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != AUTH_KEYWORD.lower().encode():
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid API key header.")
        try:
            raw_key = parts[1].decode()
        except UnicodeError as error:
            raise AuthenticationFailed("Invalid API key.") from error
        api_key = ApiKey.find_by_raw_key(raw_key)
        if api_key is None or not api_key.is_active or not api_key.tenant.is_active:
            raise AuthenticationFailed("Invalid API key.")
        self._touch(api_key)
        return TenantPrincipal(tenant=api_key.tenant, api_key=api_key), api_key

    def authenticate_header(self, request):
        return AUTH_KEYWORD

    @staticmethod
    def _touch(api_key: ApiKey) -> None:
        now = timezone.now()
        last = api_key.last_used_at
        if last is None or (now - last).total_seconds() > LAST_USED_REFRESH_SECONDS:
            ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=now)


class IsTenantAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, TenantPrincipal)
