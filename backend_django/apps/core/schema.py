from drf_spectacular.extensions import OpenApiAuthenticationExtension


class UserAccountAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.UserAccountAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
