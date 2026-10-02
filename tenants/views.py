from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from tenants.models import ApiKey
from tenants.scoping import TenantScopedViewMixin
from tenants.serializers import ApiKeySerializer, WhoAmISerializer


@extend_schema(responses=WhoAmISerializer)
@api_view(["GET"])
def whoami(request):
    tenant = request.user.tenant
    return Response({"tenant": {"id": str(tenant.id), "slug": tenant.slug, "name": tenant.name}})


class ApiKeyListView(TenantScopedViewMixin, ListAPIView):
    queryset = ApiKey.objects.all()
    serializer_class = ApiKeySerializer
