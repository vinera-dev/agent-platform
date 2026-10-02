from drf_spectacular.authentication import OpenApiAuthenticationExtension


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "tenants.authentication.ApiKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Send `Authorization: Api-Key <key>`.",
        }
