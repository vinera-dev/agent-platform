from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def whoami(request):
    tenant = request.user.tenant
    return Response({"tenant": {"id": str(tenant.id), "slug": tenant.slug, "name": tenant.name}})
