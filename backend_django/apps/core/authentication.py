import os
import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from rest_framework import authentication, exceptions, permissions
from .models import UserAccount

# Window during which a newly-registered (unverified) account may use the API. Shortened from
# the original 7 days and made configurable to reduce the unverified-access exposure window.
EMAIL_VERIFICATION_GRACE_DAYS = int(os.getenv("EMAIL_VERIFICATION_GRACE_DAYS", "3"))

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

        # Reject tokens minted before the user's current token version (e.g. password change).
        if payload.get("tv", 0) != (getattr(user, "token_version", 0) or 0):
            raise exceptions.AuthenticationFailed("Token revocado. Inicia sesión de nuevo.")

        if not user.is_email_verified:
            grace_expires = user.created_at + timedelta(days=EMAIL_VERIFICATION_GRACE_DAYS)
            if datetime.now(timezone.utc) > grace_expires:
                raise exceptions.AuthenticationFailed({
                    "detail": "Tu cuenta está bloqueada. Por favor verifica tu correo electrónico para continuar.",
                    "code": "email_verification_required",
                })

        return (user, token)


class IsAdminUser(permissions.BasePermission):
    """Only allows access to users with is_admin=True."""
    message = "Se requiere rol de administrador para esta acción."

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_admin", False))
