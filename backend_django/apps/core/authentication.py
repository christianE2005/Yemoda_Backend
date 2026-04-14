import jwt
from django.conf import settings
from rest_framework import authentication, exceptions, permissions
from .models import UserAccount

class UserAccountAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        try:
            # Expect "Bearer <token>"
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return None
            
            token = parts[1]
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token expirado.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Token invalido.")
        except Exception:
            raise exceptions.AuthenticationFailed("Error de autenticacion.")

        if payload.get("type") != "access":
            raise exceptions.AuthenticationFailed("Tipo de token incorrecto.")

        user_id = payload.get("sub")
        if not user_id:
            return None

        user = UserAccount.objects.filter(id_user=user_id).first()
        if not user:
            raise exceptions.AuthenticationFailed("Usuario no encontrado.")

        return (user, token)


class IsAdminUser(permissions.BasePermission):
    """Only allows access to users with is_admin=True."""
    message = "Se requiere rol de administrador para esta acción."

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_admin", False))
