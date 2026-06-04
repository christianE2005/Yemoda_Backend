from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from urllib.parse import urlencode, urlsplit, urlunsplit

import jwt
import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.db import models
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone as django_timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from .authentication import EMAIL_VERIFICATION_GRACE_DAYS, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (
    ActivityLog,
    Board,
    BoardColumn,
    GithubAppInstallation,
    GithubConnection,
    GithubPushEvent,
    GithubRepo,
    Milestone,
    Project,
    ProjectMember,
    ProjectRepo,
    ProjectRole,
    Role,
    Sprint,
    Tag,
    Task,
    TaskAssignment,
    TaskComment,
    TaskPriority,
    TaskPushMatch,
    TaskStatus,
    TaskAIReviewResult,
    TaskWarning,
    UserAccount,
    StripePayment,
    EmailVerificationToken,
)
from .serializers import (
    ActivityLogSerializer,
    BoardColumnSerializer,
    BoardSerializer,
    ChangePasswordSerializer,
    GithubAppLinkInstallationSerializer,
    GithubCreateRepoSerializer,
    GithubOauthCallbackSerializer,
    GithubPushEventSerializer,
    GithubRepoSerializer,
    LoginSerializer,
    MilestoneSerializer,
    ProjectMemberSerializer,
    ProjectRepoSerializer,
    ProjectRoleSerializer,
    ProjectSerializer,
    RefreshSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    RoleSerializer,
    SprintSerializer,
    TagSerializer,
    TaskAssignmentSerializer,
    TaskCommentSerializer,
    TaskPrioritySerializer,
    TaskPushMatchSerializer,
    TaskSerializer,
    TaskStatusSerializer,
    TaskAIReviewResultSerializer,
    TaskWarningSerializer,
    UserAccountSerializer,
)
from .permissions import (
    assert_can_assign_role,
    can_move_task_to_column,
    has_project_perm,
    is_project_admin,
    require_perm,
    resolve_capabilities,
    seed_default_project_roles,
)

GITHUB_API_URL = "https://api.github.com"


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug for branch names."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:50].rstrip("-")
_GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _issue_tokens(user: UserAccount) -> dict:
    access_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token_version = getattr(user, "token_version", 0) or 0
    access_payload = {
        "sub": str(user.id_user),
        "email": user.email,
        "is_admin": user.is_admin,
        "type": "access",
        "tv": token_version,
        "exp": access_expires_at,
    }
    refresh_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_REFRESH_EXPIRE_MINUTES)
    refresh_payload = {
        "sub": str(user.id_user),
        "email": user.email,
        "type": "refresh",
        "tv": token_version,
        "exp": refresh_expires_at,
    }
    access_token = jwt.encode(access_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": access_expires_at.isoformat(),
    }


def _github_headers(access_token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_app_jwt() -> str:
    if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
        raise ValueError("GITHUB_APP_ID o GITHUB_APP_PRIVATE_KEY no configurados.")
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": settings.GITHUB_APP_ID,
    }
    return jwt.encode(payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


def _github_app_headers() -> dict:
    app_jwt = _github_app_jwt()
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {app_jwt}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _refresh_github_token(connection: GithubConnection) -> bool:
    """
    Attempt to refresh the GitHub OAuth token using the stored refresh_token.
    Returns True if refreshed successfully, False otherwise.
    GitHub App expiring tokens: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens
    """
    if not connection.refresh_token:
        return False

    now = datetime.now(timezone.utc)
    if connection.refresh_token_expires_at and connection.refresh_token_expires_at <= now:
        return False

    resp = requests.post(
        _GITHUB_OAUTH_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_APP_CLIENT_ID,
            "client_secret": settings.GITHUB_APP_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        return False

    data = resp.json()
    new_token = data.get("access_token")
    if not new_token:
        return False

    connection.access_token = new_token
    if data.get("refresh_token"):
        connection.refresh_token = data["refresh_token"]
    if data.get("expires_in"):
        connection.token_expires_at = now + timedelta(seconds=int(data["expires_in"]))
    if data.get("refresh_token_expires_in"):
        connection.refresh_token_expires_at = now + timedelta(seconds=int(data["refresh_token_expires_in"]))
    connection.save()
    return True


def _get_valid_github_token(connection: GithubConnection) -> str | None:
    """Return a valid access token, refreshing it if expired."""
    now = datetime.now(timezone.utc)
    if connection.token_expires_at and connection.token_expires_at <= now:
        if not _refresh_github_token(connection):
            return None
    return connection.access_token


def _installation_access_token(installation_id: int) -> str:
    token_resp = requests.post(
        f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
        headers=_github_app_headers(),
        timeout=20,
    )
    if token_resp.status_code >= 400:
        raise ValueError(f"No se pudo obtener token de instalacion: {token_resp.text}")
    token = token_resp.json().get("token")
    if not token:
        raise ValueError("GitHub no devolvio token de instalacion.")
    return token


def _resolve_org_installation_for_user(user: UserAccount, org_login: str) -> int:
    github_connection = GithubConnection.objects.filter(user=user).first()
    if not github_connection:
        raise ValueError("El usuario no tiene GitHub conectado.")

    token = _get_valid_github_token(github_connection)
    if not token:
        raise ValueError("La conexión de GitHub del usuario expiró. Vuelve a conectar tu cuenta.")

    membership_response = requests.get(
        f"{GITHUB_API_URL}/user/memberships/orgs/{org_login}",
        headers=_github_headers(token),
        timeout=20,
    )
    if membership_response.status_code >= 400:
        raise ValueError("El usuario no pertenece a la organizacion solicitada.")
    membership = membership_response.json()
    if membership.get("state") != "active":
        raise ValueError("La membresia del usuario en la organizacion no esta activa.")

    installations_response = requests.get(
        f"{GITHUB_API_URL}/app/installations",
        headers=_github_app_headers(),
        timeout=20,
    )
    if installations_response.status_code >= 400:
        raise ValueError("No se pudieron consultar las instalaciones de GitHub App.")

    installations = installations_response.json()
    for installation in installations:
        account = installation.get("account") or {}
        if account.get("login", "").lower() == org_login.lower():
            install_obj, _ = GithubAppInstallation.objects.update_or_create(
                installation_id=installation["id"],
                defaults={
                    "account_login": account.get("login", org_login),
                    "account_type": account.get("type"),
                    "user": user,
                },
            )
            return install_obj.installation_id

    raise ValueError("La GitHub App no esta instalada en esa organizacion.")


def _add_github_collaborator(repo_full_name: str, github_login: str, admin_token: str, permission: str = "push") -> str:
    """Add a GitHub user as collaborator using the repo admin's OAuth token."""
    import logging
    logger = logging.getLogger(__name__)

    resp = requests.put(
        f"{GITHUB_API_URL}/repos/{repo_full_name}/collaborators/{github_login}",
        headers=_github_headers(admin_token),
        json={"permission": permission},
        timeout=20,
    )
    if resp.status_code >= 400:
        msg = f"github error {resp.status_code}: {resp.text}"
        logger.warning("Could not add %s as collaborator to %s: %s", github_login, repo_full_name, resp.text)
        return msg

    logger.info("Added %s as collaborator (%s) to %s.", github_login, permission, repo_full_name)
    return "ok"


def _build_signed_oauth_state(user_id: int | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "nonce": secrets.token_urlsafe(24),
        "exp": int(expires_at.timestamp()),
        "purpose": "github_app_oauth",
    }
    if user_id is not None:
        payload["uid"] = user_id
    return jwt.encode(payload, settings.GITHUB_APP_STATE_SECRET, algorithm="HS256")


# ── Email verification ────────────────────────────────────────────────────────

def _send_verification_email(user: "UserAccount") -> None:
    """Creates a new email verification token and sends the link via Resend."""
    # Invalidate any previous unused tokens for this user
    EmailVerificationToken.objects.filter(user=user, used=False).delete()

    token_value = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    EmailVerificationToken.objects.create(
        user=user,
        token=token_value,
        expires_at=expires_at,
    )

    verify_link = f"{settings.EMAIL_VERIFICATION_BASE_URL}?token={token_value}"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="color:#1a1a1a">Verifica tu correo electrónico</h2>
      <p>Hola <strong>{user.username}</strong>, gracias por registrarte en Yemoda.</p>
      <p>Haz clic en el botón de abajo para verificar tu correo. El enlace expira en <strong>24 horas</strong>.</p>
      <a href="{verify_link}"
         style="display:inline-block;padding:12px 24px;background:#4f46e5;color:#fff;
                text-decoration:none;border-radius:6px;font-weight:bold;margin:16px 0">
        Verificar correo
      </a>
      <p style="color:#666;font-size:12px">Si no creaste esta cuenta, puedes ignorar este correo.</p>
    </div>
    """
    text_body = (
        f"Hola {user.username},\n\n"
        "Gracias por registrarte en Yemoda. Por favor verifica tu correo haciendo clic en el siguiente enlace:\n\n"
        f"{verify_link}\n\n"
        "El enlace expira en 24 horas.\n\n"
        "Si no creaste esta cuenta, puedes ignorar este correo.\n\n"
        "— El equipo de Yemoda"
    )
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.RESEND_FROM_EMAIL,
            "to": [user.email],
            "subject": "Verifica tu correo — Yemoda",
            "html": html_body,
            "text": text_body,
        },
        timeout=10,
    )


def _validate_signed_oauth_state(state: str) -> tuple[bool, int | None]:
    """Returns (is_valid, user_id_from_state_or_None)."""
    try:
        payload = jwt.decode(state, settings.GITHUB_APP_STATE_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False, None
    if payload.get("purpose") != "github_app_oauth":
        return False, None
    return True, payload.get("uid")


def _user_from_bearer_token(request) -> UserAccount | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return UserAccount.objects.filter(id_user=user_id).first()


class UserAccountViewSet(viewsets.ModelViewSet):
    queryset = UserAccount.objects.select_related('github_connection').all()
    serializer_class = UserAccountSerializer

    def get_throttles(self):
        # Rate-limit the open user/email search to slow enumeration of the user base.
        if self.action == 'list' and self.request.query_params.get('search'):
            self.throttle_scope = 'user_search'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        search = self.request.query_params.get('search', '').strip()

        if search and len(search) >= 3:
            # With a search term, allow finding any non-admin user by username or email
            # (needed to add new members who don't yet share a project)
            return UserAccount.objects.select_related('github_connection').filter(
                Q(username__icontains=search) | Q(email__icontains=search),
                is_admin=False,
            ).exclude(id_user=user.id_user).distinct()[:20]

        if user.is_admin:
            return UserAccount.objects.select_related('github_connection').all()
        # Non-admins: return themselves + users who share a project with them
        # (needed for the project member picker in the frontend)
        shared_project_user_ids = (
            UserAccount.objects
            .filter(
                Q(project_memberships__project__members__user=user)
                | Q(project_memberships__project__created_by=user)
                | Q(projects_created__members__user=user)
            )
            .values_list('id_user', flat=True)
            .distinct()
        )
        return UserAccount.objects.select_related('github_connection').filter(
            Q(id_user=user.id_user) | Q(id_user__in=shared_project_user_ids)
        ).distinct()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdminUser()]
        if self.action == 'destroy':
            return [IsAdminUser()]
        if self.action in ('update', 'partial_update'):
            return [IsAuthenticated()]
        # list and retrieve: any authenticated user
        return [IsAuthenticated()]

    def perform_update(self, serializer):
        user = self.request.user
        if not user.is_admin and serializer.instance.pk != user.id_user:
            raise PermissionDenied("Solo puedes editar tu propio perfil.")
        serializer.save()


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).distinct()

    def create(self, request, *args, **kwargs):
        import logging
        try:
            return super().create(request, *args, **kwargs)
        except Exception:
            # Do not leak internals (stack trace / settings) to the client.
            logging.getLogger(__name__).exception("Project creation failed")
            return Response(
                {"detail": "No se pudo crear el proyecto."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user, status=Project.PLANNING)
        # Seed the default per-project roles (Admin/Editor/Contributor/Viewer).
        try:
            seed_default_project_roles(project)
        except Exception:
            pass
        try:
            admin_role = ProjectRole.objects.filter(project=project, is_admin_role=True).first()
            ProjectMember.objects.get_or_create(
                project=project,
                user=self.request.user,
                defaults={"role": None, "project_role": admin_role},
            )
        except Exception:
            pass

    def perform_update(self, serializer):
        # Project creator/admin or a role with can_manage_project.
        require_perm(self.request.user, serializer.instance, "can_manage_project")
        serializer.save()

    def perform_destroy(self, instance):
        # Deleting a whole project stays creator/admin-only.
        if not is_project_admin(self.request.user, instance):
            raise PermissionDenied("Solo el creador puede eliminar el proyecto.")
        instance.delete()

    @extend_schema(responses={200: dict}, tags=["projects"], summary="Capacidades del usuario actual en el proyecto")
    @action(detail=True, methods=['get'], url_path='my-permissions')
    def my_permissions(self, request, pk=None):
        """Resolved capability flags for the current user in this project (UI gating)."""
        project = self.get_object()  # get_queryset enforces membership
        return Response(resolve_capabilities(request.user, project))


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    # Requires authentication (inherits the global IsAuthenticated default) — no longer public.


class ProjectRoleViewSet(viewsets.ModelViewSet):
    """Per-project custom roles. Read for members; create/edit/delete for project admins."""
    queryset = ProjectRole.objects.all()
    serializer_class = ProjectRoleSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = ProjectRole.objects.filter(project_id__in=user_project_ids)
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs.select_related('max_move_column').order_by('id_project_role')

    def _require_admin(self, project):
        if not is_project_admin(self.request.user, project):
            raise PermissionDenied("Solo el creador del proyecto puede gestionar los roles.")

    def perform_create(self, serializer):
        self._require_admin(serializer.validated_data.get('project'))
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        self._require_admin(instance.project)
        if instance.is_admin_role:
            raise PermissionDenied("El rol de administrador no se puede modificar.")
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin(instance.project)
        if instance.is_admin_role:
            raise PermissionDenied("El rol de administrador no se puede eliminar.")
        instance.delete()


class ProjectMemberViewSet(viewsets.ModelViewSet):
    queryset = ProjectMember.objects.all()
    serializer_class = ProjectMemberSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        user = serializer.validated_data.get('user')
        if project:
            require_perm(self.request.user, project, "can_manage_members")
            assert_can_assign_role(self.request.user, project, serializer.validated_data.get('project_role'))
        if project and user and project.created_by_id == user.pk:
            raise ValidationError("El creador del proyecto ya es miembro por defecto.")
        member = serializer.save()

        # Add as GitHub collaborator if project has linked repos
        # Use the project creator's OAuth token (they have admin on the repo)
        if project and user:
            project_repos = ProjectRepo.objects.filter(project=project).values_list("repo_full_name", flat=True)
            new_user_conn = GithubConnection.objects.filter(user=user).first()
            creator_conn = GithubConnection.objects.filter(user_id=project.created_by_id).first()
            if new_user_conn and new_user_conn.github_login and creator_conn:
                admin_token = _get_valid_github_token(creator_conn)
                if admin_token:
                    for repo_full_name in project_repos:
                        _add_github_collaborator(
                            repo_full_name,
                            new_user_conn.github_login,
                            admin_token,
                        )

    def get_queryset(self):
        user = self.request.user
        user_projects = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)

        qs = ProjectMember.objects.filter(project_id__in=user_projects)

        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)

        return qs.distinct()

    def perform_update(self, serializer):
        # Assigning/changing a member's project_role requires can_manage_members, and only a
        # project admin may grant the full-access (admin) role.
        project = serializer.instance.project
        require_perm(self.request.user, project, "can_manage_members")
        new_role = serializer.validated_data.get('project_role', serializer.instance.project_role)
        assert_can_assign_role(self.request.user, project, new_role)
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        project = instance.project
        # Prevent removing the project creator
        if instance.user == project.created_by:
            raise PermissionDenied("El creador del proyecto no puede ser removido.")
        # Anyone can leave (remove themselves); removing others needs can_manage_members.
        if instance.user != user and not has_project_perm(user, project, "can_manage_members"):
            raise PermissionDenied("No tienes permiso para eliminar a otros miembros.")
        instance.delete()


class ProjectMembersView(APIView):
    @extend_schema(
        request={"application/json": {"type": "object", "properties": {
            "user_id": {"type": "integer"},
            "role_id": {"type": "integer", "nullable": True},
        }, "required": ["user_id"]}},
        responses={201: ProjectMemberSerializer, 400: dict, 404: dict},
        tags=["projects"],
    )
    def post(self, request, project_id):
        """Añade un usuario a un proyecto. Solo el creador puede agregar miembros."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not has_project_perm(request.user, project, "can_manage_members"):
            return Response({"detail": "No tienes permiso para agregar miembros."}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        user = UserAccount.objects.filter(pk=user_id).first()
        if not user:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if ProjectMember.objects.filter(project=project, user=user).exists():
            return Response({"detail": "El usuario ya es miembro del proyecto."}, status=status.HTTP_400_BAD_REQUEST)

        role_id = request.data.get("role_id")
        role = None
        if role_id:
            role = Role.objects.filter(pk=role_id).first()
            if not role:
                return Response({"detail": "Rol no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Per-project role assignment (the role system that drives authorization).
        project_role_id = request.data.get("project_role_id")
        project_role = None
        if project_role_id:
            project_role = ProjectRole.objects.filter(pk=project_role_id, project=project).first()
            if not project_role:
                return Response({"detail": "Rol de proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Only a project admin may grant the full-access (admin) role.
        assert_can_assign_role(request.user, project, project_role)

        member = ProjectMember.objects.create(project=project, user=user, role=role, project_role=project_role)

        # If the project has linked repos, add the new member as a collaborator on GitHub
        # Use the project creator's OAuth token (they have admin on the repos)
        github_collab_result = None
        project_repos = list(ProjectRepo.objects.filter(project=project).values_list("repo_full_name", flat=True))
        if project_repos:
            new_user_conn = GithubConnection.objects.filter(user=user).first()
            creator_conn = GithubConnection.objects.filter(user_id=project.created_by_id).first()
            if not new_user_conn or not new_user_conn.github_login:
                github_collab_result = "skipped: user has no GitHub connection"
            elif not creator_conn:
                github_collab_result = "skipped: project creator has no GitHub connection"
            else:
                admin_token = _get_valid_github_token(creator_conn)
                if not admin_token:
                    github_collab_result = "skipped: project creator's GitHub token expired"
                else:
                    results = []
                    for repo_full_name in project_repos:
                        results.append(_add_github_collaborator(
                            repo_full_name,
                            new_user_conn.github_login,
                            admin_token,
                        ))
                    github_collab_result = results
        else:
            github_collab_result = "skipped: project has no linked repos"

        response_data = ProjectMemberSerializer(member).data
        response_data["github_collaborator"] = github_collab_result
        return Response(response_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: ProjectMemberSerializer(many=True)},
        tags=["projects"],
    )
    def get(self, request, project_id):
        """Lista los miembros de un proyecto."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        members = ProjectMember.objects.filter(project=project)
        return Response(ProjectMemberSerializer(members, many=True).data, status=status.HTTP_200_OK)


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'board_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = Board.objects.filter(project_id__in=user_project_ids)
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            require_perm(self.request.user, project, "can_manage_board")
        serializer.save()

    def perform_update(self, serializer):
        require_perm(self.request.user, serializer.instance.project, "can_manage_board")
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.project, "can_manage_board")
        instance.delete()


class BoardColumnViewSet(viewsets.ModelViewSet):
    queryset = BoardColumn.objects.all()
    serializer_class = BoardColumnSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = BoardColumn.objects.filter(board__project_id__in=user_project_ids)
        board_id = self.request.query_params.get('board')
        if board_id is not None:
            qs = qs.filter(board_id=board_id)
        return qs

    def _enforce_single_review(self, instance):
        """If this column is marked as review, unset the flag on all others in the same board."""
        if instance.is_review:
            BoardColumn.objects.filter(board=instance.board, is_review=True).exclude(pk=instance.pk).update(is_review=False)

    def perform_create(self, serializer):
        board = serializer.validated_data.get('board')
        if board:
            require_perm(self.request.user, board.project, "can_manage_board")
        instance = serializer.save()
        self._enforce_single_review(instance)

    def perform_update(self, serializer):
        require_perm(self.request.user, serializer.instance.board.project, "can_manage_board")
        instance = serializer.save()
        self._enforce_single_review(instance)

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.board.project, "can_manage_board")
        instance.delete()

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        """Reorder board columns atomically.
        Body: [{"id_column": 1, "order": 0}, {"id_column": 2, "order": 1}, ...]
        """
        items = request.data
        if not isinstance(items, list):
            return Response({"detail": "Se esperaba una lista de {id_column, order}."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)

        column_ids = [item.get('id_column') for item in items if item.get('id_column') is not None]
        accessible = set(
            BoardColumn.objects.filter(
                id_column__in=column_ids,
                board__project_id__in=user_project_ids,
            ).values_list('id_column', flat=True)
        )
        if set(column_ids) - accessible:
            return Response({"detail": "Algunas columnas no son accesibles."}, status=status.HTTP_403_FORBIDDEN)

        # Reordering columns is a board-management action.
        affected_projects = Project.objects.filter(
            boards__columns__id_column__in=accessible
        ).distinct()
        for proj in affected_projects:
            if not has_project_perm(user, proj, "can_manage_board"):
                return Response({"detail": "Tu rol no puede gestionar el tablero."}, status=status.HTTP_403_FORBIDDEN)

        for item in items:
            col_id = item.get('id_column')
            order = item.get('order')
            if col_id is not None and order is not None:
                BoardColumn.objects.filter(id_column=col_id).update(order=order)

        return Response({"detail": "Orden actualizado."}, status=status.HTTP_200_OK)


class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all()
    serializer_class = SprintSerializer

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'sprint_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = Sprint.objects.filter(project_id__in=user_project_ids)
        project_id = self.request.query_params.get('project')
        sprint_status = self.request.query_params.get('status')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        if sprint_status is not None:
            qs = qs.filter(status=sprint_status)
        return qs

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            require_perm(self.request.user, project, "can_manage_sprints")
        serializer.save()

    def perform_update(self, serializer):
        require_perm(self.request.user, serializer.instance.project, "can_manage_sprints")
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.project, "can_manage_sprints")
        instance.delete()


class MilestoneViewSet(viewsets.ModelViewSet):
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'milestone_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = Milestone.objects.filter(project_id__in=user_project_ids)
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs

    def _validate_due_date(self, project, due_date):
        if due_date is None:
            return
        from datetime import date as date_type
        project_created_date = project.created_at.date() if hasattr(project.created_at, 'date') else project.created_at
        if isinstance(due_date, str):
            from datetime import date as _date
            due_date = _date.fromisoformat(due_date)
        if due_date < project_created_date:
            raise ValidationError(
                {"due_date": "La fecha no puede ser anterior a la creación del proyecto."}
            )

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            require_perm(self.request.user, project, "can_manage_milestones")
        due_date = serializer.validated_data.get('due_date')
        self._validate_due_date(project, due_date)
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        require_perm(self.request.user, instance.project, "can_manage_milestones")
        project = serializer.validated_data.get('project', instance.project)
        due_date = serializer.validated_data.get('due_date', instance.due_date)
        self._validate_due_date(project, due_date)
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.project, "can_manage_milestones")
        instance.delete()


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = Tag.objects.filter(project_id__in=user_project_ids)
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            require_perm(self.request.user, project, "can_manage_tags")
        serializer.save()

    def perform_update(self, serializer):
        require_perm(self.request.user, serializer.instance.project, "can_manage_tags")
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.project, "can_manage_tags")
        instance.delete()


class TaskStatusViewSet(viewsets.ModelViewSet):
    queryset = TaskStatus.objects.all()
    serializer_class = TaskStatusSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdminUser()]


class TaskPriorityViewSet(viewsets.ModelViewSet):
    queryset = TaskPriority.objects.all()
    serializer_class = TaskPrioritySerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdminUser()]


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'task_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        """
        Tasks of projects the user belongs to.
        Filters: ?project= ?sprint= ?board_column= ?milestone= ?backlog=true (sprint=NULL)
        """
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = Task.objects.filter(project_id__in=user_project_ids)

        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)

        sprint_id = self.request.query_params.get('sprint')
        if sprint_id is not None:
            qs = qs.filter(sprint_id=sprint_id)

        board_column_id = self.request.query_params.get('board_column')
        if board_column_id is not None:
            qs = qs.filter(board_column_id=board_column_id)

        milestone_id = self.request.query_params.get('milestone')
        if milestone_id is not None:
            qs = qs.filter(milestone_id=milestone_id)

        # ?backlog=true returns all tasks of the project regardless of sprint assignment
        # (Product Backlog = all tasks; sprint tasks are still part of the backlog)

        # ?parent=<id> returns the subtasks of a given task.
        # ?top_level=true returns only tasks without a parent (epics/standalone tasks).
        parent_id = self.request.query_params.get('parent')
        if parent_id is not None:
            qs = qs.filter(parent_id=parent_id)

        top_level = self.request.query_params.get('top_level')
        if top_level is not None and top_level.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(parent__isnull=True)

        tag_id = self.request.query_params.get('tag')
        if tag_id is not None:
            qs = qs.filter(tags__id_tag=tag_id)

        return qs.distinct().prefetch_related('assignments__assigned_to', 'tags', 'subtasks')

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            require_perm(self.request.user, project, "can_create_tasks")
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        project = instance.project
        data = serializer.validated_data

        # Moving a task (changing its board column) needs can_move_tasks + the role's
        # column cap; editing any other field needs can_edit_tasks.
        moving = 'board_column' in data and data['board_column'] != instance.board_column
        editing = any(field != 'board_column' for field in data.keys())

        if moving:
            allowed, reason = can_move_task_to_column(self.request.user, project, data['board_column'])
            if not allowed:
                raise PermissionDenied(reason or "Tu rol no puede mover esta tarea.")
        if editing:
            require_perm(self.request.user, project, "can_edit_tasks")
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.project, "can_delete_tasks")
        instance.delete()

    @extend_schema(
        responses={200: dict},
        tags=["tasks"],
        summary="Generar prompt IA para resolver warnings activos de una tarea",
        description=(
            "Retorna los warnings activos de la tarea y un prompt listo para copiar/pegar "
            "en otra IA para intentar resolverlos."
        ),
    )
    @action(detail=True, methods=['get'], url_path='ai-fix-prompt')
    def ai_fix_prompt(self, request, pk=None):
        task = self.get_object()
        active_warnings = list(
            TaskWarning.objects.filter(task=task, status=TaskWarning.STATUS_ACTIVE)
            .order_by('-created_at')
        )

        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        active_warnings.sort(key=lambda w: (severity_order.get(w.severity, 3), -w.id_warning))

        warnings_payload = [
            {
                'id_warning': w.id_warning,
                'severity': w.severity,
                'message': w.message,
                'created_at': w.created_at.isoformat() if w.created_at else None,
            }
            for w in active_warnings
        ]

        if warnings_payload:
            warnings_lines = "\n".join(
                f"- [{w['severity'].upper()}] (ID {w['id_warning']}): {w['message']}"
                for w in warnings_payload
            )
        else:
            warnings_lines = "- No hay warnings activos reportados para esta tarea."

        prompt_text = (
            "Actúa como senior engineer y corrige esta tarea priorizando seguridad y funcionamiento.\n\n"
            f"Tarea: {task.title}\n"
            f"Descripción: {task.description or 'Sin descripción.'}\n\n"
            "Warnings activos detectados por code review:\n"
            f"{warnings_lines}\n\n"
            "Instrucciones:\n"
            "1) Propón una solución concreta para cada warning.\n"
            "2) Entrega los cambios de código exactos por archivo.\n"
            "3) Si hay trade-offs, explica el impacto.\n"
            "4) Incluye pruebas mínimas para validar cada corrección.\n"
            "5) Mantén compatibilidad con el comportamiento actual no afectado."
        )

        return Response(
            {
                'task_id': task.id_task,
                'task_title': task.title,
                'warnings_count': len(warnings_payload),
                'warnings': warnings_payload,
                'copy_prompt': prompt_text,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=None,
        responses={202: dict, 400: dict, 502: dict},
        tags=["tasks"],
        summary="Disparar revisión IA de una tarea padre cuyas subtareas están completas",
        description=(
            "Pide al servicio de IA que revise la tarea padre usando el último push del "
            "proyecto. Solo procede si la tarea tiene subtareas y todas están completadas. "
            "Pensado para llamarse al marcar la última subtarea."
        ),
    )
    @action(detail=True, methods=['post'], url_path='ai-review')
    def ai_review(self, request, pk=None):
        task = self.get_object()  # get_queryset already enforces project membership
        require_perm(request.user, task.project, "can_trigger_ai")

        subtasks = list(task.subtasks.all())
        if not subtasks:
            return Response(
                {"detail": "La tarea no tiene subtareas; no aplica la revisión por completitud."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        open_subtasks = [s for s in subtasks if s.completed_at is None]
        if open_subtasks:
            return Response(
                {"detail": f"Aún hay {len(open_subtasks)} subtarea(s) sin completar.", "open_subtasks": len(open_subtasks)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base = (settings.FASTAPI_CHAT_BASE_URL or "").rstrip("/")
        if not base:
            return Response(
                {"detail": "El servicio de IA no está configurado (FASTAPI_CHAT_BASE_URL)."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            resp = requests.post(
                f"{base}/webhook/review-task/",
                json={"project_id": task.project_id, "task_id": task.id_task},
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Token": settings.GITHUB_APP_WEBHOOK_SECRET or "",
                },
                timeout=5,
            )
        except requests.RequestException as exc:
            return Response(
                {"detail": "No se pudo contactar al servicio de IA.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if resp.status_code >= 400:
            return Response(
                {"detail": "El servicio de IA rechazó la solicitud.", "status": resp.status_code},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"detail": "Revisión con IA solicitada. La tarea se actualizará en segundo plano."},
            status=status.HTTP_202_ACCEPTED,
        )


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.all()
    serializer_class = TaskCommentSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = TaskComment.objects.filter(task__project_id__in=user_project_ids)
        task_id = self.request.query_params.get('task')
        if task_id is not None:
            qs = qs.filter(task_id=task_id)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        if task:
            require_perm(self.request.user, task.project, "can_comment")
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        comment = serializer.instance
        if comment.user != user and comment.task.project.created_by != user:
            raise PermissionDenied("Solo puedes editar tus propios comentarios.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.user != user and instance.task.project.created_by != user:
            raise PermissionDenied("Solo puedes eliminar tus propios comentarios.")
        instance.delete()


class TaskAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAssignment.objects.all()
    serializer_class = TaskAssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(members__user=user) | Q(created_by=user)
        ).values_list('id_project', flat=True)
        qs = TaskAssignment.objects.filter(task__project_id__in=user_project_ids)
        task_id = self.request.query_params.get('task')
        user_id_param = self.request.query_params.get('user')
        if task_id is not None:
            qs = qs.filter(task_id=task_id)
        if user_id_param is not None:
            qs = qs.filter(assigned_to_id=user_id_param)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data.get('task')
        if task:
            require_perm(self.request.user, task.project, "can_edit_tasks")
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request.user, instance.task.project, "can_edit_tasks")
        instance.delete()


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    # Read-only: activity logs are written server-side, never created/edited via the API.
    serializer_class = ActivityLogSerializer
    queryset = ActivityLog.objects.none()  # needed for router basename resolution

    def get_queryset(self):
        user = self.request.user

        # All project IDs that have at least one repo in project_repo table
        projects_with_repos = ProjectRepo.objects.values_list("project_id", flat=True).distinct()

        # User's projects that also have repos (not personal projects without repos)
        user_project_ids = Project.objects.filter(
            Q(created_by=user) | Q(members__user=user),
            id_project__in=projects_with_repos,
        ).distinct().values_list("id_project", flat=True)

        # Only show logs that are explicitly linked to one of those projects
        qs = ActivityLog.objects.filter(
            project_id__in=user_project_ids
        ).order_by("-created_at")

        project_id = self.request.query_params.get("project_id")
        if project_id:
            qs = qs.filter(project_id=project_id)

        return qs

    def perform_create(self, serializer):
        # If the frontend sends project_id, use it; otherwise leave null
        serializer.save(user=self.request.user)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserAccountSerializer, 400: dict},
        tags=["auth"],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        if UserAccount.objects.filter(email=email).exists():
            return Response({"detail": "El correo ya esta registrado."}, status=status.HTTP_400_BAD_REQUEST)

        user = UserAccount.objects.create(
            email=email,
            username=username,
            password_hash=make_password(password),
        )
        try:
            _send_verification_email(user)
        except Exception:
            pass  # Never block registration if email delivery fails
        return Response(
            {"detail": "Registro exitoso. Revisa tu correo para verificar tu cuenta."},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={200: dict, 401: dict},
        tags=["auth"],
        auth=[],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = UserAccount.objects.filter(email=email).first()
        if not user or not check_password(password, user.password_hash):
            return Response({"detail": "Credenciales invalidas."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_email_verified:
            grace_expires = user.created_at + timedelta(days=EMAIL_VERIFICATION_GRACE_DAYS)
            if datetime.now(timezone.utc) > grace_expires:
                return Response(
                    {
                        "detail": "Tu cuenta está bloqueada. Por favor verifica tu correo electrónico para continuar.",
                        "code": "email_verification_required",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Within 7-day grace period — allow login

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": UserAccountSerializer(user).data}, status=status.HTTP_200_OK)


class RefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    @extend_schema(
        request=RefreshSerializer,
        responses={200: dict, 401: dict},
        tags=["auth"],
    )
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh_token"]

        try:
            payload = jwt.decode(
                refresh_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Refresh token expirado."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Refresh token invalido."}, status=status.HTTP_401_UNAUTHORIZED)

        if payload.get("type") != "refresh":
            return Response({"detail": "Tipo de token invalido."}, status=status.HTTP_401_UNAUTHORIZED)

        user = UserAccount.objects.filter(id_user=payload.get("sub")).first()
        if not user:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_401_UNAUTHORIZED)

        # Reject refresh tokens minted before the current token version (revoked sessions).
        if payload.get("tv", 0) != (getattr(user, "token_version", 0) or 0):
            return Response({"detail": "Sesión revocada. Inicia sesión de nuevo."}, status=status.HTTP_401_UNAUTHORIZED)

        tokens = _issue_tokens(user)
        return Response(
            {
                "access_token": tokens["access_token"],
                "token_type": tokens["token_type"],
                "expires_at": tokens["expires_at"],
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "change_password"

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: dict, 400: dict},
        tags=["auth"],
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not check_password(current_password, request.user.password_hash):
            return Response({"detail": "Contraseña actual incorrecta."}, status=status.HTTP_400_BAD_REQUEST)

        # Rotate the token version so every previously-issued JWT (access + refresh) is
        # invalidated, then hand back fresh tokens so the current client stays logged in.
        request.user.password_hash = make_password(new_password)
        request.user.token_version = (getattr(request.user, "token_version", 0) or 0) + 1
        request.user.save(update_fields=["password_hash", "token_version"])
        tokens = _issue_tokens(request.user)
        return Response(
            {"detail": "Contraseña actualizada correctamente.", **tokens},
            status=status.HTTP_200_OK,
        )


class VerifyEmailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={302: None},
        tags=["auth"],
        summary="Verificar correo electrónico (GET — retrocompatibilidad)",
        description="Link de correo heredado. Verifica el token y redirige al frontend.",
    )
    def get(self, request):
        """Flujo heredado: el link del correo va directamente al backend."""
        token_value = request.query_params.get("token", "")
        redirect_base = settings.EMAIL_VERIFIED_REDIRECT

        if not token_value:
            return HttpResponseRedirect(f"{redirect_base}?error=missing_token")

        now = datetime.now(timezone.utc)
        record = EmailVerificationToken.objects.select_related("user").filter(
            token=token_value, used=False, expires_at__gt=now
        ).first()

        if not record:
            return HttpResponseRedirect(f"{redirect_base}?error=invalid_or_expired_token")

        record.used = True
        record.save(update_fields=["used"])
        record.user.is_email_verified = True
        record.user.save(update_fields=["is_email_verified"])

        return HttpResponseRedirect(f"{redirect_base}?success=true")

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}},
        responses={200: dict, 400: dict},
        tags=["auth"],
        summary="Verificar correo electrónico (POST — recomendado)",
        description="El frontend envía el token por POST. Los scanners de email no hacen POST, por lo que evita la auto-verificación.",
    )
    def post(self, request):
        """Flujo recomendado: el frontend lee el token de la URL y hace POST al backend."""
        token_value = request.data.get("token", "")
        if not token_value:
            return Response({"detail": "Token requerido."}, status=status.HTTP_400_BAD_REQUEST)

        now = datetime.now(timezone.utc)
        record = EmailVerificationToken.objects.select_related("user").filter(
            token=token_value, used=False, expires_at__gt=now
        ).first()

        if not record:
            return Response({"detail": "Token inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)

        record.used = True
        record.save(update_fields=["used"])
        record.user.is_email_verified = True
        record.user.save(update_fields=["is_email_verified"])

        return Response({"detail": "Correo verificado correctamente."}, status=status.HTTP_200_OK)


class ResendVerificationEmailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "resend_verification"

    @extend_schema(
        request=ResendVerificationSerializer,
        responses={200: dict},
        tags=["auth"],
        summary="Reenviar correo de verificación",
    )
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        # Always return 200 to avoid email enumeration
        user = UserAccount.objects.filter(email=email, is_email_verified=False).first()
        if user:
            try:
                _send_verification_email(user)
            except Exception:
                pass

        return Response(
            {"detail": "Si el correo existe y no está verificado, recibirás un nuevo enlace."},
            status=status.HTTP_200_OK,
        )


# ── Google OAuth ──────────────────────────────────────────────────────────────
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _build_google_oauth_state(nickname: str | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "nonce": secrets.token_urlsafe(24),
        "exp": int(expires_at.timestamp()),
        "purpose": "google_oauth",
    }
    if nickname:
        payload["nickname"] = nickname.strip()
    return jwt.encode(payload, settings.GOOGLE_STATE_SECRET, algorithm="HS256")


def _decode_google_oauth_state(state: str) -> dict | None:
    try:
        payload = jwt.decode(state, settings.GOOGLE_STATE_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != "google_oauth":
        return None
    return payload


def _generate_unique_username(base_name: str) -> str:
    base = (base_name or "").strip() or "user"
    base = re.sub(r"\s+", " ", base)[:100].strip()
    if not base:
        base = "user"

    candidate = base
    suffix = 1
    while UserAccount.objects.filter(username__iexact=candidate).exists():
        suffix += 1
        tail = f" {suffix}"
        candidate = f"{base[: max(1, 100 - len(tail))]}{tail}"
    return candidate


class GoogleOauthStartView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={302: None, 503: dict},
        tags=["auth"],
        summary="Iniciar flujo OAuth con Google",
        description="Redirige al usuario a la URL de autorización de Google.",
    )
    def get(self, request):
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
            return Response(
                {"detail": "Google OAuth no está configurado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        state = _build_google_oauth_state()
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        return HttpResponseRedirect(auth_url)


class GoogleOauthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={302: None, 400: dict},
        tags=["auth"],
        summary="Callback de Google OAuth",
        description="Google redirige aquí con el código de autorización. El backend lo intercambia, crea o recupera el usuario y redirige al frontend con los tokens JWT.",
    )
    def get(self, request):
        frontend_redirect = (settings.GOOGLE_AUTH_FRONTEND_REDIRECT or "").strip()
        if not frontend_redirect:
            frontend_redirect = "https://yemoda.site/auth/google/callback"

        # Defensive fallback: if env points to site root, force the callback path.
        parsed_redirect = urlsplit(frontend_redirect)
        if parsed_redirect.scheme and parsed_redirect.netloc:
            normalized_path = parsed_redirect.path or "/auth/google/callback"
            if normalized_path == "/":
                normalized_path = "/auth/google/callback"
            elif normalized_path.endswith("/") and normalized_path != "/":
                normalized_path = normalized_path.rstrip("/")
            frontend_redirect = urlunsplit(
                (
                    parsed_redirect.scheme,
                    parsed_redirect.netloc,
                    normalized_path,
                    parsed_redirect.query,
                    parsed_redirect.fragment,
                )
            )
        elif frontend_redirect == "/":
            frontend_redirect = "/auth/google/callback"

        error = request.query_params.get("error")
        code = request.query_params.get("code")
        state = request.query_params.get("state", "")
        oauth_payload = _decode_google_oauth_state(state)

        if error or not code:
            return HttpResponseRedirect(f"{frontend_redirect}?error={error or 'no_code'}")

        if not oauth_payload:
            return HttpResponseRedirect(f"{frontend_redirect}?error=invalid_state")

        # Exchange authorization code for Google access token
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if not token_resp.ok:
            return HttpResponseRedirect(f"{frontend_redirect}?error=token_exchange_failed")

        google_access_token = token_resp.json().get("access_token")
        if not google_access_token:
            return HttpResponseRedirect(f"{frontend_redirect}?error=no_access_token")

        # Fetch user info from Google
        userinfo_resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
            timeout=15,
        )
        if not userinfo_resp.ok:
            return HttpResponseRedirect(f"{frontend_redirect}?error=userinfo_failed")

        userinfo = userinfo_resp.json()
        email = userinfo.get("email")
        if not email:
            return HttpResponseRedirect(f"{frontend_redirect}?error=no_email")

        # Auto-register new users on first Google login (Google already verified the email)
        user = UserAccount.objects.filter(email=email).first()
        needs_nickname = False
        if not user:
            display_name = (userinfo.get("name") or "").strip()
            fallback_name = email.split("@")[0]
            generated_username = _generate_unique_username(display_name or fallback_name)

            user = UserAccount.objects.create(
                email=email,
                username=generated_username,
                password_hash=make_password(None),  # unusable — Google-only login
                is_email_verified=True,
            )
            needs_nickname = True
        # Google already verified the email — always mark verified regardless of how the account was created
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

        tokens = _issue_tokens(user)
        # Deliver tokens in the URL fragment (#), not the query string: fragments are not sent
        # to servers, so they don't leak via the Referer header or proxy/server access logs.
        redirect_url = (
            f"{frontend_redirect}"
            f"#access_token={tokens['access_token']}"
            f"&refresh_token={tokens['refresh_token']}"
            f"&expires_at={tokens['expires_at']}"
            f"&needs_nickname={'1' if needs_nickname else '0'}"
        )
        return HttpResponseRedirect(redirect_url)


class GithubAppInstallStartView(APIView):
    """
    Endpoint reservado para administradores de la organización.
    Los usuarios normales NO deben usar este endpoint — la App ya está instalada en la org.
    El flujo de usuarios es únicamente OAuth (/api/github/app/oauth/start/).
    """
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: dict, 403: dict, 500: dict}, tags=["github-app"])
    def get(self, request):
        if not settings.GITHUB_APP_SLUG:
            return Response({"detail": "GITHUB_APP_SLUG no configurado."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        install_url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
        return Response({"install_url": install_url}, status=status.HTTP_200_OK)


class GithubAppOauthStartView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_oauth"

    @extend_schema(responses={200: dict, 500: dict}, tags=["github-app"])
    def get(self, request):
        if not settings.GITHUB_APP_CLIENT_ID or not settings.GITHUB_APP_OAUTH_CALLBACK_URL:
            return Response(
                {"detail": "GITHUB_APP_CLIENT_ID o GITHUB_APP_OAUTH_CALLBACK_URL no configurados."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not settings.GITHUB_APP_SLUG:
            return Response(
                {"detail": "GITHUB_APP_SLUG no configurado."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user = _user_from_bearer_token(request)
        state = _build_signed_oauth_state(user_id=getattr(user, 'id_user', None))
        params = {
            "state": state,
            "redirect_uri": settings.GITHUB_APP_OAUTH_CALLBACK_URL,
        }

        # If the user already has the GitHub App installed on their account, skip
        # the installation page and go straight to OAuth authorization.
        # Otherwise, send them to the installation page which installs the App AND
        # triggers OAuth in one step (requires "Request user authorization during
        # installation" enabled in the GitHub App settings).
        already_installed = (
            user is not None
            and GithubAppInstallation.objects.filter(user=user).exists()
        )
        if already_installed:
            authorize_url = (
                f"https://github.com/login/oauth/authorize?{urlencode(params)}"
                f"&client_id={settings.GITHUB_APP_CLIENT_ID}"
            )
        else:
            authorize_url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?{urlencode(params)}"

        return Response({"authorize_url": authorize_url, "state": state}, status=status.HTTP_200_OK)


class GithubAppOauthCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GithubOauthCallbackSerializer, responses={200: dict, 400: dict, 401: dict, 500: dict}, tags=["github-app"])
    def _complete_oauth(self, request, code: str, state: str) -> tuple[dict | None, str | None, int]:
        valid, state_user_id = _validate_signed_oauth_state(state)
        if not valid:
            return None, "OAuth state invalido.", status.HTTP_400_BAD_REQUEST

        if not settings.GITHUB_APP_CLIENT_ID or not settings.GITHUB_APP_CLIENT_SECRET:
            return None, "Credenciales OAuth de GitHub App incompletas.", status.HTTP_500_INTERNAL_SERVER_ERROR

        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_APP_CLIENT_ID,
                "client_secret": settings.GITHUB_APP_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_APP_OAUTH_CALLBACK_URL,
            },
            timeout=20,
        )
        if token_response.status_code >= 400:
            return None, "No se pudo obtener access token de GitHub.", status.HTTP_400_BAD_REQUEST

        token_resp_json = token_response.json()
        if token_resp_json.get("error"):
            return None, f"GitHub OAuth error: {token_resp_json.get('error_description', token_resp_json['error'])}", status.HTTP_400_BAD_REQUEST

        access_token = token_resp_json.get("access_token")
        if not access_token:
            return None, "GitHub no devolvio access_token.", status.HTTP_400_BAD_REQUEST

        user_response = requests.get(f"{GITHUB_API_URL}/user", headers=_github_headers(access_token), timeout=20)
        if user_response.status_code >= 400:
            return None, "No se pudo obtener usuario de GitHub.", status.HTTP_400_BAD_REQUEST
        github_user = user_response.json()
        github_login = github_user.get("login")
        github_user_id = github_user.get("id")
        if not github_login or not github_user_id:
            return None, "GitHub no devolvio datos validos de usuario.", status.HTTP_400_BAD_REQUEST

        token_user = _user_from_bearer_token(request)
        if request.method == "POST" and not token_user:
            return None, "Authorization Bearer requerido para vincular GitHub al usuario actual.", status.HTTP_401_UNAUTHORIZED

        # For GET callbacks (browser redirects), use the user_id embedded in the state JWT
        # since no Bearer token is available in browser redirects.
        if not token_user and state_user_id:
            token_user = UserAccount.objects.filter(id_user=state_user_id).first()

        user = token_user
        if not user:
            emails_response = requests.get(f"{GITHUB_API_URL}/user/emails", headers=_github_headers(access_token), timeout=20)
            email = None
            if emails_response.status_code < 400:
                emails = emails_response.json()
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                fallback = next((e for e in emails if e.get("verified")), None)
                chosen = primary or fallback
                if chosen:
                    email = chosen.get("email")
            if not email:
                email = github_user.get("email") or f"{github_login}@users.noreply.github.com"

            user = UserAccount.objects.filter(email=email).first()
            if not user:
                user = UserAccount.objects.create(
                    email=email,
                    username=github_login,
                    password_hash=make_password(None),
                )

        existing_connection = GithubConnection.objects.filter(github_user_id=github_user_id).first()
        if existing_connection and existing_connection.user_id != user.id_user:
            if state_user_id and user.id_user == state_user_id:
                # The current user is explicitly authenticated via the state JWT and just
                # completed GitHub OAuth for this account — they own it. Re-assign the
                # connection (the old link was likely a ghost account from a prior attempt).
                existing_connection.user_id = user.id_user
                existing_connection.save(update_fields=["user_id"])
            else:
                return None, "Esta cuenta de GitHub ya esta vinculada con otro usuario.", status.HTTP_400_BAD_REQUEST

        token_data = token_resp_json
        now = datetime.now(timezone.utc)
        github_connection_defaults = {
            "github_user_id": github_user_id,
            "github_login": github_login,
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token"),
            "token_expires_at": (
                now + timedelta(seconds=int(token_data["expires_in"]))
                if token_data.get("expires_in") else None
            ),
            "refresh_token_expires_at": (
                now + timedelta(seconds=int(token_data["refresh_token_expires_in"]))
                if token_data.get("refresh_token_expires_in") else None
            ),
        }
        GithubConnection.objects.update_or_create(
            user=user,
            defaults=github_connection_defaults,
        )

        tokens = _issue_tokens(user)
        return (
            {
                **tokens,
                "user": UserAccountSerializer(user).data,
                "github_login": github_login,
            },
            None,
            status.HTTP_200_OK,
        )

    def get(self, request):
        frontend_redirect = settings.GITHUB_AUTH_FRONTEND_REDIRECT
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        installation_id = request.query_params.get("installation_id")

        if not code or not state:
            return HttpResponseRedirect(f"{frontend_redirect}?error=missing_code_or_state")

        payload, error, status_code = self._complete_oauth(request, code=code, state=state)
        if error:
            return HttpResponseRedirect(f"{frontend_redirect}?error={urlencode({'msg': error})}")

        # If installation_id is present (from the App installation+OAuth combined flow),
        # save it so the user's personal installation is linked to their account.
        if installation_id:
            try:
                inst_id_int = int(installation_id)
                user_data = payload.get("user", {})
                user_id = user_data.get("id_user") if isinstance(user_data, dict) else None
                if user_id:
                    user_obj = UserAccount.objects.filter(id_user=user_id).first()
                    if user_obj:
                        github_login = payload.get("github_login", "")
                        GithubAppInstallation.objects.update_or_create(
                            installation_id=inst_id_int,
                            defaults={
                                "user": user_obj,
                                "account_login": github_login,
                                "account_type": "User",
                            },
                        )
            except (ValueError, TypeError):
                pass

        # Tokens go in the URL fragment (#), not the query string — fragments aren't sent to
        # servers, avoiding Referer / access-log leakage of the bearer + refresh tokens.
        redirect_url = (
            f"{frontend_redirect}"
            f"#access_token={payload['access_token']}"
            f"&refresh_token={payload['refresh_token']}"
            f"&expires_at={payload['expires_at']}"
        )
        return HttpResponseRedirect(redirect_url)

    def post(self, request):
        serializer = GithubOauthCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload, error, status_code = self._complete_oauth(
            request,
            code=serializer.validated_data["code"],
            state=serializer.validated_data["state"],
        )
        if error:
            return Response({"detail": error}, status=status_code)
        return Response(payload, status=status_code)


class GithubAppLinkInstallationView(APIView):
    @extend_schema(request=GithubAppLinkInstallationSerializer, responses={200: dict, 400: dict, 404: dict}, tags=["github-app"])
    def post(self, request):
        serializer = GithubAppLinkInstallationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installation_id = serializer.validated_data["installation_id"]

        # Always link the installation to the authenticated caller — never a body-supplied
        # user_id (which would let an attacker hijack installations onto other accounts).
        user = request.user

        try:
            installation_response = requests.get(
                f"{GITHUB_API_URL}/app/installations/{installation_id}",
                headers=_github_app_headers(),
                timeout=20,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if installation_response.status_code >= 400:
            return Response(
                {"detail": "No se pudo consultar la instalacion."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = installation_response.json()
        account = data.get("account") or {}
        install, _ = GithubAppInstallation.objects.update_or_create(
            installation_id=installation_id,
            defaults={
                "account_login": account.get("login", ""),
                "account_type": account.get("type"),
                "user": user,
            },
        )
        return Response(
            {
                "installation_id": install.installation_id,
                "account_login": install.account_login,
                "account_type": install.account_type,
                "user_id": user.id_user,
            },
            status=status.HTTP_200_OK,
        )


class GithubCreateRepoView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_repo_create"

    @extend_schema(responses={200: GithubRepoSerializer(many=True)}, tags=["github-app"])
    def get(self, request):
        """
        Lista los repositorios del proyecto especificado.
        Requiere: ?project_id=<id>
        """
        project_id = request.query_params.get("project_id")
        if not project_id:
            return Response(
                {"detail": "project_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        project = Project.objects.filter(
            Q(id_project=project_id) & (Q(members__user=user) | Q(created_by=user))
        ).distinct().first()
        if not project:
            return Response(
                {"detail": "Proyecto no encontrado o no tienes acceso."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = GithubRepo.objects.filter(project_id=project_id)
        return Response(GithubRepoSerializer(qs, many=True).data)

    @extend_schema(request=GithubCreateRepoSerializer, responses={201: dict, 400: dict, 404: dict}, tags=["github-app"])
    def post(self, request):
        serializer = GithubCreateRepoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Act only as the authenticated caller — never a body-supplied user_id (which would
        # let an attacker create repos with another user's GitHub token / org installation).
        user = request.user

        owner_type = data["owner_type"]
        owner = data.get("owner") or ""
        auth_headers = None
        create_url = ""

        if owner_type == "user":
            github_connection = GithubConnection.objects.filter(user=user).first()
            if not github_connection:
                return Response({"detail": "El usuario no tiene GitHub conectado."}, status=status.HTTP_400_BAD_REQUEST)
            token = _get_valid_github_token(github_connection)
            if not token:
                return Response(
                    {"detail": "La conexión de GitHub expiró. Vuelve a conectar tu cuenta."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            auth_headers = _github_headers(token)
            create_url = f"{GITHUB_API_URL}/user/repos"
        else:
            if not owner:
                return Response({"detail": "Para owner_type=org, owner es requerido."}, status=status.HTTP_400_BAD_REQUEST)
            installation_id = data.get("installation_id")
            if not installation_id:
                linked = GithubAppInstallation.objects.filter(user=user, account_login=owner).first()
                installation_id = linked.installation_id if linked else None
            if isinstance(installation_id, int) and installation_id > 0:
                resolved_installation_id = installation_id
            else:
                resolved_installation_id = None
            if not resolved_installation_id:
                try:
                    resolved_installation_id = _resolve_org_installation_for_user(user=user, org_login=owner)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as exc:
                    return Response(
                        {"detail": f"Error de configuración GitHub App: {exc}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            try:
                token = _installation_access_token(resolved_installation_id)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                return Response(
                    {"detail": f"Error generando token de instalación: {exc}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            auth_headers = _github_headers(token)
            create_url = f"{GITHUB_API_URL}/orgs/{owner}/repos"

        create_repo_payload = {
            "name": data["name"],
            "description": data.get("description") or "",
            "private": data["private"],
            "auto_init": data["auto_init"],
        }
        repo_response = requests.post(create_url, headers=auth_headers, json=create_repo_payload, timeout=20)
        if repo_response.status_code >= 400:
            # Surface GitHub's user-facing `message` only (e.g. "name already exists"),
            # never the raw response body.
            try:
                gh_error = repo_response.json().get("message", "")
            except Exception:
                gh_error = ""
            return Response(
                {"detail": f"GitHub: {gh_error}" if gh_error else "No se pudo crear el repositorio en GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repo = repo_response.json()

        project_id = data["project_id"]
        project_obj = Project.objects.filter(
            Q(id_project=project_id) & (Q(members__user=user) | Q(created_by=user))
        ).distinct().first()
        if not project_obj:
            return Response(
                {"detail": "Proyecto no encontrado o no tienes acceso."},
                status=status.HTTP_404_NOT_FOUND,
            )

        Project.objects.filter(id_project=project_id).update(
            github_repo_full_name=repo.get("full_name")
        )
        project_obj.refresh_from_db()

        # Register in project_repo (multi-repo support)
        ProjectRepo.objects.get_or_create(
            project=project_obj,
            repo_full_name=repo.get("full_name"),
        )

        # Always persist the repo so it can be listed later
        GithubRepo.objects.update_or_create(
            github_repo_id=repo["id"],
            defaults={
                "user": user,
                "project": project_obj,
                "full_name": repo.get("full_name", ""),
                "name": repo.get("name", ""),
                "owner": (repo.get("owner") or {}).get("login", owner or ""),
                "private": repo.get("private", True),
                "html_url": repo.get("html_url", ""),
            },
        )

        # For org repos (created via App token), add the user as collaborator
        # so they can push. The repo was created by the bot, not the user.
        if owner_type == "org":
            github_connection = GithubConnection.objects.filter(user=user).first()
            if github_connection and github_connection.github_login:
                collab_response = requests.put(
                    f"{GITHUB_API_URL}/repos/{repo['full_name']}/collaborators/{github_connection.github_login}",
                    headers=auth_headers,
                    json={"permission": "admin"},
                    timeout=20,
                )
                if collab_response.status_code >= 400:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Could not add %s as collaborator to %s: %s",
                        github_connection.github_login,
                        repo["full_name"],
                        collab_response.text,
                    )

        # Sync existing project members as collaborators (push permission)
        # Uses the creator's OAuth token since they now have admin on the repo
        creator_conn = GithubConnection.objects.filter(user=user).first()
        creator_token = _get_valid_github_token(creator_conn) if creator_conn else None
        if creator_token:
            existing_members = ProjectMember.objects.filter(
                project=project_obj
            ).exclude(user=user).select_related("user")
            for member in existing_members:
                member_conn = GithubConnection.objects.filter(user=member.user).first()
                if member_conn and member_conn.github_login:
                    _add_github_collaborator(
                        repo["full_name"],
                        member_conn.github_login,
                        creator_token,
                    )

        # Always use the server-configured webhook target — never a client-supplied URL
        # (which would let an attacker register the repo's webhook against an arbitrary host).
        webhook_url = settings.GITHUB_APP_WEBHOOK_TARGET_URL
        if not webhook_url:
            return Response(
                {
                    "detail": "Repositorio creado, pero falta configurar GITHUB_APP_WEBHOOK_TARGET_URL en el servidor.",
                    "repository": repo,
                },
                status=status.HTTP_201_CREATED,
            )

        webhook_payload = {
            "name": "web",
            "active": True,
            "events": ["push"],
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": settings.GITHUB_APP_WEBHOOK_SECRET or "",
                "insecure_ssl": "0",
            },
        }
        hooks_response = requests.post(
            f"{GITHUB_API_URL}/repos/{repo['full_name']}/hooks",
            headers=auth_headers,
            json=webhook_payload,
            timeout=20,
        )
        if hooks_response.status_code >= 400:
            return Response(
                {
                    "detail": "Repositorio creado, pero fallo la creacion del webhook.",
                    "repository": repo,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response({"repository": repo, "webhook": hooks_response.json()}, status=status.HTTP_201_CREATED)


class GithubDeleteRepoView(APIView):
    @extend_schema(responses={204: None, 403: dict, 404: dict}, tags=["github-app"])
    def delete(self, request, repo_id):
        """Desvincula un repositorio de YeMoDa (no lo borra en GitHub)."""
        repo = GithubRepo.objects.filter(pk=repo_id).first()
        if not repo:
            return Response({"detail": "Repositorio no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if repo.user_id != request.user.id_user:
            return Response({"detail": "No tienes permiso para desvincular este repositorio."}, status=status.HTTP_403_FORBIDDEN)
        # Remove the ProjectRepo entry so future member invitations skip this repo
        if repo.project_id:
            ProjectRepo.objects.filter(project_id=repo.project_id, repo_full_name=repo.full_name).delete()
            # Clear the project's primary repo field if it points to this repo
            Project.objects.filter(id_project=repo.project_id, github_repo_full_name=repo.full_name).update(github_repo_full_name=None)
        repo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GithubPushWebhookView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_webhook"

    @extend_schema(request=dict, responses={200: dict, 400: dict, 401: dict}, tags=["github-app"])
    def post(self, request):
        payload_bytes = request.body
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Fail closed: a missing secret means we cannot authenticate the webhook, so reject
        # rather than accept unsigned requests that mutate data / trigger AI processing.
        webhook_secret = settings.GITHUB_APP_WEBHOOK_SECRET
        if not webhook_secret:
            return Response(
                {"detail": "Webhook no disponible: GITHUB_APP_WEBHOOK_SECRET no está configurado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        expected = "sha256=" + hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return Response({"detail": "Firma de webhook invalida."}, status=status.HTTP_401_UNAUTHORIZED)

        event = request.headers.get("X-GitHub-Event", "")
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            return Response({"detail": "Payload JSON invalido."}, status=status.HTTP_400_BAD_REQUEST)

        installation = payload.get("installation") or {}
        account = (payload.get("installation") or {}).get("account") or (payload.get("organization") or {}) or {}
        installation_id = installation.get("id")
        if installation_id and account.get("login"):
            GithubAppInstallation.objects.update_or_create(
                installation_id=installation_id,
                defaults={
                    "account_login": account.get("login"),
                    "account_type": account.get("type"),
                },
            )

        if event != "push":
            return Response({"detail": f"Evento ignorado: {event}"}, status=status.HTTP_200_OK)

        commits = payload.get("commits", [])
        commit_summaries = []
        for commit in commits:
            commit_summaries.append(
                {
                    "id": commit.get("id"),
                    "message": commit.get("message"),
                    "author": (commit.get("author") or {}).get("name"),
                    "added": commit.get("added", []),
                    "modified": commit.get("modified", []),
                    "removed": commit.get("removed", []),
                }
            )

        repo_full_name = (payload.get("repository") or {}).get("full_name", "")
        ref = payload.get("ref", "")
        pusher_name = (payload.get("pusher") or {}).get("name")

        project = (
            Project.objects.filter(repos__repo_full_name__iexact=repo_full_name).first()
            or Project.objects.filter(github_repo_full_name__iexact=repo_full_name).first()
        )
        GithubPushEvent.objects.create(
            project=project,
            repo_full_name=repo_full_name,
            ref=ref,
            pusher=pusher_name,
            commits=commit_summaries,
        )

        # Forward the original GitHub payload to the FastAPI AI agent
        agent_url = settings.GITHUB_APP_WEBHOOK_TARGET_URL
        agent_forward = {"url": agent_url or None, "status": None, "error": None}
        if agent_url:
            try:
                fwd = requests.post(
                    agent_url,
                    data=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Event": event,
                        "X-Hub-Signature-256": signature,
                    },
                    timeout=5,
                )
                agent_forward["status"] = fwd.status_code
            except Exception as e:
                agent_forward["error"] = str(e)

        return Response(
            {
                "repository": repo_full_name,
                "ref": ref,
                "pusher": pusher_name,
                "installation_id": installation_id,
                "total_commits": len(commits),
                "commits": commit_summaries,
                "agent_forward": agent_forward,
            },
            status=status.HTTP_200_OK,
        )


class GithubPushListView(APIView):
    @extend_schema(responses={200: GithubPushEventSerializer(many=True)}, tags=["github-app"])
    def get(self, request):
        """
        Retorna los push events de los proyectos del usuario.
        Filtros opcionales: ?project_id=1  o  ?repo=owner/repo
        """
        user = request.user
        user_project_ids = list(
            Project.objects.filter(
                Q(members__user=user) | Q(created_by=user)
            ).values_list('id_project', flat=True)
        )

        repo = request.query_params.get("repo")
        project_id = request.query_params.get("project_id")

        if repo:
            # When filtering by repo, include events regardless of project linkage
            # (some events may have project=null if the fallback path was used).
            # Security: verify the user owns/belongs to a project tied to this repo.
            user_repos = ProjectRepo.objects.filter(
                project_id__in=user_project_ids,
                repo_full_name__iexact=repo,
            )
            has_access = user_repos.exists() or Project.objects.filter(
                id_project__in=user_project_ids,
                github_repo_full_name__iexact=repo,
            ).exists()
            if not has_access:
                return Response([], status=status.HTTP_200_OK)
            qs = GithubPushEvent.objects.filter(repo_full_name__iexact=repo)
        else:
            qs = GithubPushEvent.objects.filter(project_id__in=user_project_ids)
            if project_id:
                qs = qs.filter(project_id=project_id)

        qs = qs.order_by("-received_at")[:50]
        serializer = GithubPushEventSerializer(qs, many=True)
        return Response(serializer.data)


def _user_can_access_repo(user, repo_full_name: str) -> bool:
    """True only if the user is a member/creator of a project linked to repo_full_name.

    Used to gate repo-scoped GitHub endpoints so an authenticated user can't mint an org
    installation token for, and read/write, repositories they have no project relationship to.
    """
    if not repo_full_name:
        return False
    project_ids = Project.objects.filter(
        Q(members__user=user) | Q(created_by=user)
    ).values_list("id_project", flat=True)
    return (
        ProjectRepo.objects.filter(project_id__in=project_ids, repo_full_name__iexact=repo_full_name).exists()
        or Project.objects.filter(id_project__in=project_ids, github_repo_full_name__iexact=repo_full_name).exists()
    )


class GithubCommitDiffView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_repo_contents"

    @extend_schema(responses={200: dict, 400: dict}, tags=["github-app"])
    def get(self, request):
        """
        Retorna el diff de un commit específico.
        Parámetros requeridos: ?repo=owner/repo&commit=SHA
        Usa el installation token de la org para autenticarse.
        """
        repo = request.query_params.get("repo", "").strip()
        commit_sha = request.query_params.get("commit", "").strip()

        if not repo or not commit_sha:
            return Response(
                {"detail": "Se requieren los parámetros 'repo' y 'commit'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _user_can_access_repo(request.user, repo):
            return Response({"detail": "No tienes acceso a este repositorio."}, status=status.HTTP_403_FORBIDDEN)

        # Find installation for this repo's org
        org_login = repo.split("/")[0] if "/" in repo else repo
        installation = GithubAppInstallation.objects.filter(
            account_login__iexact=org_login
        ).first()

        if not installation:
            return Response(
                {"detail": f"No se encontró instalación de GitHub App para '{org_login}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = _installation_access_token(installation.installation_id)
        except (ValueError, Exception) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        diff_response = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/commits/{commit_sha}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.diff",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

        if diff_response.status_code >= 400:
            return Response(
                {"detail": "No se pudo obtener el diff."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Also get the commit metadata (files list + stats)
        meta_response = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/commits/{commit_sha}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )
        meta = meta_response.json() if meta_response.ok else {}
        commit_info = meta.get("commit", {})
        files = [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "patch": f.get("patch"),  # per-file diff
            }
            for f in meta.get("files", [])
        ]

        return Response(
            {
                "repo": repo,
                "commit": commit_sha,
                "message": commit_info.get("message"),
                "author": (commit_info.get("author") or {}).get("name"),
                "date": (commit_info.get("author") or {}).get("date"),
                "stats": meta.get("stats", {}),
                "files": files,
                "diff": diff_response.text,
            }
        )


class GithubRepoContentsView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_repo_contents"

    @extend_schema(responses={200: dict, 400: dict}, tags=["github-app"])
    def get(self, request):
        """
        Navega los archivos de un repositorio usando la GitHub Contents API.

        Parámetros requeridos: ?repo=owner/repo
        Parámetros opcionales:
          ?path=src/components   (subcarpeta, default raíz)
          ?ref=main              (branch/tag/SHA, default branch por defecto del repo)
        """
        repo = request.query_params.get("repo", "").strip()
        path = request.query_params.get("path", "").strip("/")
        ref = request.query_params.get("ref", "").strip()

        if not repo:
            return Response({"detail": "El parámetro 'repo' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        if not _user_can_access_repo(request.user, repo):
            return Response({"detail": "No tienes acceso a este repositorio."}, status=status.HTTP_403_FORBIDDEN)

        org_login = repo.split("/")[0] if "/" in repo else repo
        installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()

        token = None
        if installation:
            try:
                token = _installation_access_token(installation.installation_id)
            except Exception:
                token = None

        # Fallback: use the authenticated user's personal OAuth token
        if not token:
            conn = GithubConnection.objects.filter(user=request.user).first()
            if conn:
                token = _get_valid_github_token(conn)

        if not token:
            return Response(
                {"detail": f"No se pudo obtener token de instalacion para '{org_login}'. Conecta tu cuenta de GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"{GITHUB_API_URL}/repos/{repo}/contents/{path}"
        params = {}
        if ref:
            params["ref"] = ref

        response = requests.get(
            url,
            headers=_github_headers(token),
            params=params,
            timeout=20,
        )

        if response.status_code == 404:
            return Response({"detail": "Ruta no encontrada en el repositorio."}, status=status.HTTP_404_NOT_FOUND)
        if response.status_code >= 400:
            return Response({"detail": "Error al obtener contenidos."}, status=status.HTTP_400_BAD_REQUEST)

        data = response.json()

        # Single file — decode base64 content
        if isinstance(data, dict) and data.get("type") == "file":
            import base64
            raw_content = data.get("content", "")
            try:
                decoded = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            except Exception:
                decoded = None
            return Response({
                "type": "file",
                "name": data.get("name"),
                "path": data.get("path"),
                "size": data.get("size"),
                "sha": data.get("sha"),
                "html_url": data.get("html_url"),
                "download_url": data.get("download_url"),
                "content": decoded,
            })

        # Directory — return listing without file content
        items = [
            {
                "type": item.get("type"),   # "file" or "dir"
                "name": item.get("name"),
                "path": item.get("path"),
                "size": item.get("size"),
                "sha": item.get("sha"),
                "html_url": item.get("html_url"),
            }
            for item in (data if isinstance(data, list) else [])
        ]
        # Directories first, then files, both alphabetically
        items.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
        return Response({"type": "dir", "path": path or "/", "items": items})


class TaskWarningListView(APIView):
    @extend_schema(responses={200: TaskWarningSerializer(many=True)}, tags=["warnings"])
    def get(self, request):
        """
        Retorna warnings de tareas.
        Filtros: ?task_id=1  ?status=active|resolved  ?project_id=1
        Sin filtros: devuelve solo warnings de proyectos del usuario autenticado.
        """
        user = request.user
        user_project_ids = Project.objects.filter(
            Q(created_by=user) | Q(members__user=user)
        ).distinct().values_list("id_project", flat=True)

        qs = TaskWarning.objects.select_related("task").filter(task__project_id__in=user_project_ids)

        task_id = request.query_params.get("task_id")
        warn_status = request.query_params.get("status")
        project_id = request.query_params.get("project_id")

        if task_id:
            qs = qs.filter(task_id=task_id)
        if warn_status:
            qs = qs.filter(status=warn_status)
        if project_id:
            qs = qs.filter(task__project_id=project_id)

        serializer = TaskWarningSerializer(qs[:100], many=True)
        return Response(serializer.data)


class TaskAIReviewResultViewSet(viewsets.ModelViewSet):
    queryset = TaskAIReviewResult.objects.select_related("task", "user").all()
    serializer_class = TaskAIReviewResultSerializer

    def get_queryset(self):
        user = self.request.user
        user_project_ids = Project.objects.filter(
            Q(created_by=user) | Q(members__user=user)
        ).distinct().values_list("id_project", flat=True)

        qs = TaskAIReviewResult.objects.select_related("task", "user").filter(task__project_id__in=user_project_ids)
        task_id = self.request.query_params.get("task")
        if task_id:
            qs = qs.filter(task_id=task_id)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data.get("task")
        if not task:
            raise ValidationError({"task": "task es requerido."})

        user = self.request.user
        user_id = getattr(user, "id_user", None) or getattr(user, "id", None)
        if not user_id:
            raise PermissionDenied("No se pudo identificar al usuario autenticado.")

        if task.project.created_by_id != user_id and not ProjectMember.objects.filter(project=task.project, user_id=user_id).exists():
            raise PermissionDenied("No tienes acceso a esta tarea.")

        serializer.save(user=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except DatabaseError:
            task_obj = serializer.validated_data.get("task")
            provider = serializer.validated_data.get("provider")
            model_name = serializer.validated_data.get("model_name")
            result_text = serializer.validated_data.get("result_text")
            user = request.user
            user_id = getattr(user, "id_user", None) or getattr(user, "id", None)

            fallback_payload = {
                "id_review_result": 0,
                "task": getattr(task_obj, "id_task", None) or getattr(task_obj, "pk", None),
                "user": user_id,
                "provider": provider,
                "model_name": model_name,
                "result_text": result_text,
                "created_at": django_timezone.now().isoformat(),
                "persisted": False,
            }
            return Response(fallback_payload, status=status.HTTP_200_OK)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "integer"}}}, "required": ["ids"]}},
        responses={200: dict},
        tags=["warnings"],
    )
    def delete(self, request):
        """Bulk delete warnings by ID list. Body: {\"ids\": [1, 2, 3]}"""
        ids = request.data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return Response({"detail": "ids es requerido y debe ser una lista."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        user_project_ids = Project.objects.filter(
            Q(created_by=user) | Q(members__user=user)
        ).distinct().values_list("id_project", flat=True)

        deleted_count, _ = TaskWarning.objects.filter(
            pk__in=ids,
            task__project_id__in=user_project_ids,
        ).delete()
        return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)


class TaskWarningDetailView(APIView):
    @extend_schema(responses={204: None, 403: dict, 404: dict}, tags=["warnings"])
    def delete(self, request, warning_id: int):
        """Elimina un warning. Solo miembros del proyecto al que pertenece la tarea pueden borrarlo."""
        warning = TaskWarning.objects.select_related("task__project").filter(pk=warning_id).first()
        if not warning:
            return Response({"detail": "Warning no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        project = warning.task.project
        user = request.user
        is_member = (
            project.created_by == user
            or ProjectMember.objects.filter(project=project, user=user).exists()
        )
        if not is_member:
            return Response({"detail": "No tienes permiso para eliminar este warning."}, status=status.HTTP_403_FORBIDDEN)

        warning.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskHistoryView(APIView):
    @extend_schema(
        responses={200: TaskPushMatchSerializer(many=True)},
        tags=["tasks"],
        summary="Get push history for a task",
        description=(
            "Returns all GitHub push matches linked to a user story, including the relevant "
            "code snippet, coverage assessment and reason provided by the AI agent."
        ),
    )
    def get(self, request, task_id: int):
        task = Task.objects.select_related("project").filter(pk=task_id).first()
        if not task:
            return Response({"detail": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        # Only members/creator of the task's project may read its push history (diffs/snippets).
        is_member = (
            task.project.created_by_id == getattr(request.user, "id_user", None)
            or ProjectMember.objects.filter(project=task.project, user=request.user).exists()
        )
        if not is_member:
            return Response({"detail": "No tienes acceso a esta tarea."}, status=status.HTTP_403_FORBIDDEN)

        matches = (
            TaskPushMatch.objects.select_related("push")
            .filter(task_id=task_id)
            .order_by("-created_at")
        )
        serializer = TaskPushMatchSerializer(matches, many=True)
        return Response(serializer.data)


# ── Pull Request / Reviews ────────────────────────────────────────────────────

def _get_user_github_token(user: UserAccount) -> str:
    """Return a valid OAuth token for the user or raise ValueError."""
    connection = GithubConnection.objects.filter(user=user).first()
    if not connection:
        raise ValueError("No tienes una cuenta de GitHub conectada.")
    token = _get_valid_github_token(connection)
    if not token:
        raise ValueError("Tu conexión de GitHub expiró. Vuelve a conectar tu cuenta.")
    return token


def _installation_token_for_repo(repo_full_name: str) -> str | None:
    """Return a GitHub App installation token for the given repo's org, or None."""
    org_login = repo_full_name.split("/")[0]
    installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()
    if not installation:
        return None
    try:
        return _installation_access_token(installation.installation_id)
    except Exception:
        return None


def _pr_token(user: UserAccount, repo_full_name: str) -> tuple[str, bool]:
    """Return (token, is_app_token) for repo-level GitHub API calls."""
    app_token = _installation_token_for_repo(repo_full_name)
    if app_token:
        return app_token, True
    user_token = _get_user_github_token(user)  # raises ValueError if not connected
    return user_token, False


class PullRequestListView(APIView):
    @extend_schema(
        parameters=[
            {"name": "tab", "in": "query", "schema": {"type": "string", "enum": ["for_me", "created"]}, "description": "for_me: PRs where the user is reviewer or assignee. created: PRs authored by the user."},
            {"name": "state", "in": "query", "schema": {"type": "string", "enum": ["open", "closed", "all"]}, "description": "PR state filter (default: open)."},
            {"name": "project_id", "in": "query", "schema": {"type": "integer"}, "description": "Scope results to repos of a specific project."},
        ],
        responses={200: dict},
        tags=["reviews"],
        summary="List pull requests associated with the authenticated user",
    )
    def get(self, request):
        tab = (request.query_params.get("tab") or "for_me").strip()
        state = (request.query_params.get("state") or "open").strip()
        project_id = request.query_params.get("project_id")

        try:
            token = _get_user_github_token(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        connection = GithubConnection.objects.filter(user=request.user).first()
        login = connection.github_login

        # Build repo scope qualifier if project_id provided
        repo_qualifier = ""
        if project_id:
            try:
                project = Project.objects.get(pk=int(project_id))
                repos = list(
                    ProjectRepo.objects.filter(project=project).values_list("repo_full_name", flat=True)
                )
                if project.github_repo_full_name and project.github_repo_full_name not in repos:
                    repos.append(project.github_repo_full_name)
                if repos:
                    repo_qualifier = " ".join(f"repo:{r}" for r in repos[:8])
            except (Project.DoesNotExist, ValueError):
                pass

        if state not in ("open", "closed", "all"):
            state = "open"
        state_q = "is:open" if state == "open" else ("is:closed" if state == "closed" else "")

        if tab == "created":
            queries = [f"type:pr {state_q} author:{login} {repo_qualifier}".strip()]
        else:
            # for_me: review-requested + assignee (deduplicated)
            queries = [
                f"type:pr {state_q} review-requested:{login} {repo_qualifier}".strip(),
                f"type:pr {state_q} assignee:{login} {repo_qualifier}".strip(),
            ]

        headers = _github_headers(token)
        seen: set[int] = set()
        prs: list[dict] = []

        for query in queries:
            resp = requests.get(
                f"{GITHUB_API_URL}/search/issues",
                headers=headers,
                params={"q": query, "per_page": 50, "sort": "updated"},
                timeout=20,
            )
            if resp.status_code >= 400:
                continue
            for item in resp.json().get("items", []):
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                # repository_url: https://api.github.com/repos/owner/repo
                repo_api_url = item.get("repository_url", "")
                repo_full = "/".join(repo_api_url.split("/")[-2:]) if repo_api_url else ""
                pr_meta = item.get("pull_request", {})
                prs.append({
                    "number": item["number"],
                    "title": item["title"],
                    "state": item["state"],
                    "draft": item.get("draft", False),
                    "repo": repo_full,
                    "url": item["html_url"],
                    "author": {
                        "login": item["user"]["login"],
                        "avatar_url": item["user"]["avatar_url"],
                    },
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "comments": item.get("comments", 0),
                    "labels": [lbl["name"] for lbl in item.get("labels", [])],
                    "assignees": [
                        {"login": a["login"], "avatar_url": a["avatar_url"]}
                        for a in item.get("assignees", [])
                    ],
                    "merged_at": pr_meta.get("merged_at"),
                })

        prs.sort(key=lambda p: p["updated_at"], reverse=True)
        return Response({"tab": tab, "total_count": len(prs), "prs": prs})


class PullRequestDetailView(APIView):
    @extend_schema(
        parameters=[
            {"name": "repo", "in": "query", "required": True, "schema": {"type": "string"}, "description": "owner/repo"},
            {"name": "pr", "in": "query", "required": True, "schema": {"type": "integer"}, "description": "PR number"},
        ],
        responses={200: dict, 400: dict, 404: dict},
        tags=["reviews"],
        summary="Get PR details including reviews, comments, and CI checks",
    )
    def get(self, request):
        repo = (request.query_params.get("repo") or "").strip()
        pr_raw = request.query_params.get("pr")
        if not repo or not pr_raw:
            return Response({"detail": "Parámetros 'repo' y 'pr' requeridos."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pr_number = int(pr_raw)
        except (TypeError, ValueError):
            return Response({"detail": "'pr' debe ser un número entero."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token, _ = _pr_token(request.user, repo)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        headers = _github_headers(token)
        base_url = f"{GITHUB_API_URL}/repos/{repo}"

        pr_resp = requests.get(f"{base_url}/pulls/{pr_number}", headers=headers, timeout=20)
        if pr_resp.status_code == 404:
            return Response({"detail": "PR no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if pr_resp.status_code >= 400:
            return Response({"detail": "Error consultando el PR en GitHub."}, status=status.HTTP_400_BAD_REQUEST)
        pr = pr_resp.json()

        reviews_resp = requests.get(f"{base_url}/pulls/{pr_number}/reviews", headers=headers, timeout=20)
        reviews = []
        if reviews_resp.status_code == 200:
            for r in reviews_resp.json():
                reviews.append({
                    "id": r["id"],
                    "user": {"login": r["user"]["login"], "avatar_url": r["user"]["avatar_url"]},
                    "state": r["state"],
                    "body": r.get("body") or "",
                    "submitted_at": r.get("submitted_at"),
                    "html_url": r.get("html_url", ""),
                })

        comments_resp = requests.get(
            f"{base_url}/issues/{pr_number}/comments",
            headers=headers,
            params={"per_page": 100},
            timeout=20,
        )
        comments = []
        if comments_resp.status_code == 200:
            for c in comments_resp.json():
                comments.append({
                    "id": c["id"],
                    "user": {"login": c["user"]["login"], "avatar_url": c["user"]["avatar_url"]},
                    "body": c["body"],
                    "created_at": c["created_at"],
                    "updated_at": c["updated_at"],
                    "html_url": c.get("html_url", ""),
                })

        head_sha = pr.get("head", {}).get("sha", "")
        checks = []
        if head_sha:
            checks_resp = requests.get(
                f"{base_url}/commits/{head_sha}/check-runs",
                headers=headers,
                params={"per_page": 50},
                timeout=20,
            )
            if checks_resp.status_code == 200:
                for ch in checks_resp.json().get("check_runs", []):
                    checks.append({
                        "name": ch["name"],
                        "status": ch["status"],
                        "conclusion": ch.get("conclusion"),
                        "url": ch.get("html_url", ""),
                        "started_at": ch.get("started_at"),
                        "completed_at": ch.get("completed_at"),
                    })

        return Response({
            "number": pr["number"],
            "title": pr["title"],
            "body": pr.get("body") or "",
            "state": pr["state"],
            "draft": pr.get("draft", False),
            "merged": pr.get("merged", False),
            "mergeable": pr.get("mergeable"),
            "repo": repo,
            "url": pr["html_url"],
            "author": {
                "login": pr["user"]["login"],
                "avatar_url": pr["user"]["avatar_url"],
            },
            "head_branch": pr["head"]["ref"],
            "base_branch": pr["base"]["ref"],
            "head_sha": head_sha,
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            "requested_reviewers": [
                {"login": r["login"], "avatar_url": r["avatar_url"]}
                for r in pr.get("requested_reviewers", [])
            ],
            "assignees": [
                {"login": a["login"], "avatar_url": a["avatar_url"]}
                for a in pr.get("assignees", [])
            ],
            "labels": [lbl["name"] for lbl in pr.get("labels", [])],
            "reviews": reviews,
            "comments": comments,
            "checks": checks,
        })


class PullRequestFilesView(APIView):
    @extend_schema(
        parameters=[
            {"name": "repo", "in": "query", "required": True, "schema": {"type": "string"}, "description": "owner/repo"},
            {"name": "pr", "in": "query", "required": True, "schema": {"type": "integer"}, "description": "PR number"},
        ],
        responses={200: dict, 400: dict, 404: dict},
        tags=["reviews"],
        summary="Get PR changed files with per-file unified diffs",
    )
    def get(self, request):
        repo = (request.query_params.get("repo") or "").strip()
        pr_raw = request.query_params.get("pr")
        if not repo or not pr_raw:
            return Response({"detail": "Parámetros 'repo' y 'pr' requeridos."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pr_number = int(pr_raw)
        except (TypeError, ValueError):
            return Response({"detail": "'pr' debe ser un número entero."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token, _ = _pr_token(request.user, repo)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}/files",
            headers=_github_headers(token),
            params={"per_page": 100},
            timeout=30,
        )
        if resp.status_code == 404:
            return Response({"detail": "PR no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if resp.status_code >= 400:
            return Response({"detail": "Error obteniendo archivos del PR."}, status=status.HTTP_400_BAD_REQUEST)

        files = []
        for f in resp.json():
            files.append({
                "filename": f["filename"],
                "status": f["status"],          # added / modified / removed / renamed
                "additions": f["additions"],
                "deletions": f["deletions"],
                "changes": f["changes"],
                "patch": f.get("patch") or "",  # unified diff; may be empty for binary files
                "blob_url": f.get("blob_url") or "",
                "raw_url": f.get("raw_url") or "",
                "previous_filename": f.get("previous_filename"),  # present on renames
            })
        return Response({"files": files, "total": len(files)})


class PullRequestReviewView(APIView):
    @extend_schema(
        parameters=[
            {"name": "repo", "in": "query", "required": True, "schema": {"type": "string"}, "description": "owner/repo"},
            {"name": "pr", "in": "query", "required": True, "schema": {"type": "integer"}, "description": "PR number"},
        ],
        request={"application/json": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"]},
                "body": {"type": "string"},
            },
            "required": ["event"],
        }},
        responses={201: dict, 400: dict, 404: dict},
        tags=["reviews"],
        summary="Submit a review on a PR (approve, request changes, or comment)",
    )
    def post(self, request):
        repo = (request.query_params.get("repo") or "").strip()
        pr_raw = request.query_params.get("pr")
        if not repo or not pr_raw:
            return Response({"detail": "Parámetros 'repo' y 'pr' requeridos."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pr_number = int(pr_raw)
        except (TypeError, ValueError):
            return Response({"detail": "'pr' debe ser un número entero."}, status=status.HTTP_400_BAD_REQUEST)

        event = (request.data.get("event") or "").upper().strip()
        if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
            return Response(
                {"detail": "'event' debe ser APPROVE, REQUEST_CHANGES o COMMENT."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = (request.data.get("body") or "").strip()
        if event in ("REQUEST_CHANGES", "COMMENT") and not body:
            return Response(
                {"detail": f"'body' es requerido para el evento '{event}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = _get_user_github_token(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload: dict = {"event": event}
        if body:
            payload["body"] = body

        resp = requests.post(
            f"{GITHUB_API_URL}/repos/{repo}/pulls/{pr_number}/reviews",
            headers=_github_headers(token),
            json=payload,
            timeout=20,
        )
        if resp.status_code == 404:
            return Response({"detail": "PR no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if resp.status_code >= 400:
            return Response(
                {"detail": "Error enviando el review a GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review = resp.json()
        return Response(
            {
                "id": review["id"],
                "state": review["state"],
                "body": review.get("body") or "",
                "submitted_at": review.get("submitted_at"),
                "html_url": review.get("html_url", ""),
            },
            status=status.HTTP_201_CREATED,
        )


class PullRequestCommentView(APIView):
    @extend_schema(
        parameters=[
            {"name": "repo", "in": "query", "required": True, "schema": {"type": "string"}, "description": "owner/repo"},
            {"name": "pr", "in": "query", "required": True, "schema": {"type": "integer"}, "description": "PR number"},
        ],
        request={"application/json": {
            "type": "object",
            "properties": {"body": {"type": "string"}},
            "required": ["body"],
        }},
        responses={201: dict, 400: dict, 404: dict},
        tags=["reviews"],
        summary="Post a general comment on a PR",
    )
    def post(self, request):
        repo = (request.query_params.get("repo") or "").strip()
        pr_raw = request.query_params.get("pr")
        if not repo or not pr_raw:
            return Response({"detail": "Parámetros 'repo' y 'pr' requeridos."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pr_number = int(pr_raw)
        except (TypeError, ValueError):
            return Response({"detail": "'pr' debe ser un número entero."}, status=status.HTTP_400_BAD_REQUEST)

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "'body' no puede estar vacío."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = _get_user_github_token(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        resp = requests.post(
            f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments",
            headers=_github_headers(token),
            json={"body": body},
            timeout=20,
        )
        if resp.status_code == 404:
            return Response({"detail": "PR no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if resp.status_code >= 400:
            return Response(
                {"detail": "Error publicando el comentario en GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = resp.json()
        return Response(
            {
                "id": comment["id"],
                "body": comment["body"],
                "html_url": comment.get("html_url", ""),
                "created_at": comment["created_at"],
            },
            status=status.HTTP_201_CREATED,
        )


class TaskPullRequestsView(APIView):
    @extend_schema(
        responses={200: dict, 403: dict, 404: dict},
        tags=["tasks"],
        summary="List PRs associated with a task (matched by branch name prefix {task_id}-)",
    )
    def get(self, request, task_id: int):
        user = request.user
        task = Task.objects.select_related("project").filter(pk=task_id).first()
        if not task:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        project = task.project
        has_access = (
            project.created_by_id == user.id_user
            or ProjectMember.objects.filter(project=project, user=user).exists()
        )
        if not has_access:
            return Response({"detail": "No tienes acceso a este proyecto."}, status=status.HTTP_403_FORBIDDEN)

        project_repo = ProjectRepo.objects.filter(project=project).first()
        repo_full_name = (
            (project_repo.repo_full_name if project_repo else None)
            or project.github_repo_full_name
        )
        if not repo_full_name:
            return Response({"task_id": task_id, "prs": []})

        try:
            token, _ = _pr_token(user, repo_full_name)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        prefix = f"{task_id}-"
        prs: list[dict] = []

        for state in ("open", "closed"):
            resp = requests.get(
                f"{GITHUB_API_URL}/repos/{repo_full_name}/pulls",
                headers=_github_headers(token),
                params={"state": state, "per_page": 100},
                timeout=20,
            )
            if resp.status_code >= 400:
                continue
            for pr in resp.json():
                head_ref = pr.get("head", {}).get("ref", "")
                if not (head_ref.startswith(prefix) or head_ref == str(task_id)):
                    continue
                prs.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "draft": pr.get("draft", False),
                    "merged": pr.get("merged", False),
                    "url": pr["html_url"],
                    "author": {
                        "login": pr["user"]["login"],
                        "avatar_url": pr["user"]["avatar_url"],
                    },
                    "head_branch": head_ref,
                    "base_branch": pr["base"]["ref"],
                    "created_at": pr["created_at"],
                    "updated_at": pr["updated_at"],
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changed_files", 0),
                    "requested_reviewers": [
                        {"login": r["login"], "avatar_url": r["avatar_url"]}
                        for r in pr.get("requested_reviewers", [])
                    ],
                })

        prs.sort(key=lambda p: p["updated_at"], reverse=True)
        return Response({"task_id": task_id, "repo": repo_full_name, "prs": prs})


class TaskCreateBranchView(APIView):
    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"base_branch": {"type": "string"}}, "required": ["base_branch"]}},
        responses={201: dict, 400: dict, 403: dict, 404: dict, 409: dict},
        tags=["tasks"],
        summary="Create GitHub branch for a task",
        description="Creates a branch named '{task_id}-{slug}' in the project's GitHub repo and returns the git checkout command.",
    )
    def post(self, request, task_id: int):
        base_branch = (request.data.get("base_branch") or "").strip()
        if not base_branch:
            return Response({"detail": "base_branch es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        requested_repo = (request.data.get("repo_full_name") or "").strip()

        user = request.user
        task = Task.objects.select_related("project").filter(pk=task_id).first()
        if not task:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        project = task.project
        has_access = (
            project.created_by_id == user.id_user
            or ProjectMember.objects.filter(project=project, user=user).exists()
        )
        if not has_access:
            return Response({"detail": "No tienes acceso a este proyecto."}, status=status.HTTP_403_FORBIDDEN)

        project_repos = list(
            ProjectRepo.objects.filter(project=project).values_list("repo_full_name", flat=True)
        )
        if not project_repos:
            return Response(
                {"detail": "El proyecto no tiene repositorios de GitHub vinculados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if requested_repo:
            if requested_repo not in project_repos:
                return Response(
                    {"detail": "No tienes permiso para crear branches en ese repositorio."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            repo_full_name = requested_repo
        else:
            if len(project_repos) > 1:
                return Response(
                    {"detail": "El proyecto tiene varios repositorios vinculados. Especifica repo_full_name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            repo_full_name = project_repos[0]

        org_login = repo_full_name.split("/")[0]
        installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()

        token = None
        if installation:
            try:
                token = _installation_access_token(installation.installation_id)
            except Exception:
                token = None  # fall through to user OAuth token

        if not token:
            # Fallback: use the requesting user's OAuth token (covers personal repos
            # where no installation exists or the installation_id is stale).
            github_connection = GithubConnection.objects.filter(user=user).first()
            if github_connection:
                token = _get_valid_github_token(github_connection)
            if not token:
                return Response(
                    {"detail": f"No se encontró instalación de GitHub App para '{org_login}' ni token OAuth del usuario. Conecta tu cuenta de GitHub."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        headers = _github_headers(token)

        ref_resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo_full_name}/git/ref/heads/{base_branch}",
            headers=headers,
            timeout=20,
        )
        if ref_resp.status_code == 404:
            return Response(
                {"detail": f"La rama base '{base_branch}' no existe."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ref_resp.status_code >= 400:
            return Response(
                {"detail": "Error consultando la rama base en GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sha = ref_resp.json().get("object", {}).get("sha")
        if not sha:
            return Response({"detail": "No se pudo obtener el SHA de la rama base."}, status=status.HTTP_400_BAD_REQUEST)

        slug = _slugify(task.title)
        branch_name = f"{task_id}-{slug}" if slug else str(task_id)

        create_resp = requests.post(
            f"{GITHUB_API_URL}/repos/{repo_full_name}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            timeout=20,
        )
        if create_resp.status_code == 422:
            return Response(
                {"detail": f"La rama '{branch_name}' ya existe en GitHub."},
                status=status.HTTP_409_CONFLICT,
            )
        if create_resp.status_code >= 400:
            return Response(
                {"detail": "Error creando la rama en GitHub."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "branch_name": branch_name,
                "checkout_command": f"git fetch origin && git checkout {branch_name}",
            },
            status=status.HTTP_201_CREATED,
        )


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


# Jerarquía de planes: valores más altos indican mayor nivel.
_PLAN_RANK = {"monthly": 1, "annual": 2}


class CreateCheckoutSessionView(APIView):
    def post(self, request):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        plan = (request.data.get("plan") or "monthly").strip().lower()
        if plan not in _PLAN_RANK:
            return Response(
                {"detail": "Plan inválido. Usa 'monthly' o 'annual'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        current_plan = user.subscription_plan  # None, 'monthly' o 'annual'

        if current_plan is not None:
            current_rank = _PLAN_RANK.get(current_plan, 0)
            requested_rank = _PLAN_RANK[plan]

            if requested_rank <= current_rank:
                # Mismo nivel o downgrade: no permitido
                msg = (
                    f"Ya tienes el plan '{current_plan}' activo."
                    if requested_rank == current_rank
                    else f"No puedes pasar del plan '{current_plan}' a '{plan}' (downgrade no permitido)."
                )
                return Response(
                    {
                        "detail": msg,
                        "current_plan": current_plan,
                        "requested_plan": plan,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            # requested_rank > current_rank → upgrade permitido

        if plan == "annual":
            price_id = settings.STRIPE_PRICE_ID_ANNUAL
        else:
            price_id = settings.STRIPE_PRICE_ID_MONTHLY

        if not price_id:
            return Response(
                {"detail": f"STRIPE_PRICE_ID_{plan.upper()} not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            session = stripe.checkout.Session.create(
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=settings.STRIPE_SUCCESS_URL,
                cancel_url=settings.STRIPE_CANCEL_URL,
                customer_email=user.email,
                metadata={"user_id": str(user.id_user), "plan": plan},
            )
        except stripe.StripeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        StripePayment.objects.create(
            user=user,
            checkout_session_id=session.id,
            plan=plan,
            status=StripePayment.PENDING,
        )

        return Response({"checkout_url": session.url}, status=status.HTTP_201_CREATED)


class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)

        if event["type"] == "checkout.session.completed":
            from django.utils import timezone
            session_data = event["data"]["object"]
            session_id = session_data.get("id")

            try:
                payment = StripePayment.objects.get(checkout_session_id=session_id)
            except StripePayment.DoesNotExist:
                return Response(status=status.HTTP_200_OK)

            payment.status = StripePayment.COMPLETED
            payment.stripe_customer_id = session_data.get("customer")
            payment.amount_total = session_data.get("amount_total")
            payment.currency = session_data.get("currency")
            payment.completed_at = timezone.now()

            # Persistir el plan desde metadata (fuente de verdad: la sesión de Stripe)
            plan_from_meta = (session_data.get("metadata") or {}).get("plan") or payment.plan
            if plan_from_meta in ("monthly", "annual"):
                payment.plan = plan_from_meta

            payment.save()

            user = payment.user
            # Audit only: the user↔plan binding comes from the server-created session, so a
            # mismatching paying email is not a grant decision — but log it for traceability.
            paid_email = (session_data.get("customer_details") or {}).get("email") or session_data.get("customer_email")
            if paid_email and user.email and paid_email.strip().lower() != user.email.strip().lower():
                import logging
                logging.getLogger(__name__).warning(
                    "Stripe checkout %s: paying email differs from account email (user_id=%s).",
                    session_id, user.id_user,
                )
            user.is_premium = True
            # Guardar IDs de Stripe en el usuario para poder cancelar/gestionar después
            stripe_customer_id = session_data.get("customer")
            stripe_subscription_id = session_data.get("subscription")
            if stripe_customer_id:
                user.stripe_customer_id = stripe_customer_id
            if stripe_subscription_id:
                user.stripe_subscription_id = stripe_subscription_id
            # Solo actualizar el plan si es un upgrade o primer plan
            current_rank = _PLAN_RANK.get(user.subscription_plan, 0)
            new_rank = _PLAN_RANK.get(plan_from_meta, 0)
            update_fields = ["is_premium", "stripe_customer_id", "stripe_subscription_id"]
            if new_rank > current_rank:
                user.subscription_plan = plan_from_meta
                update_fields.append("subscription_plan")
            user.save(update_fields=update_fields)

        elif event["type"] == "customer.subscription.deleted":
            # Stripe confirma la cancelación efectiva (al final del período o inmediata)
            sub_data = event["data"]["object"]
            stripe_sub_id = sub_data.get("id")
            if stripe_sub_id:
                from apps.core.models import UserAccount as _UserAccount
                affected = _UserAccount.objects.filter(stripe_subscription_id=stripe_sub_id)
                affected.update(
                    is_premium=False,
                    subscription_plan=None,
                    stripe_subscription_id=None,
                )

        return Response(status=status.HTTP_200_OK)


class CancelSubscriptionView(APIView):
    @extend_schema(
        request=None,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string"},
                    "cancel_at_period_end": {"type": "boolean"},
                    "current_period_end": {"type": "integer", "nullable": True},
                },
            },
            400: dict,
            404: dict,
            502: dict,
        },
        tags=["payments"],
        summary="Cancelar suscripción activa",
        description=(
            "Marca la suscripción de Stripe para cancelarse al final del período de facturación "
            "actual. El usuario conserva acceso premium hasta esa fecha; "
            "el webhook 'customer.subscription.deleted' revocará el acceso automáticamente."
        ),
    )
    def post(self, request):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        user = request.user

        if not user.is_premium or not user.stripe_subscription_id:
            return Response(
                {"detail": "No tienes una suscripción activa para cancelar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subscription = stripe.Subscription.modify(
                user.stripe_subscription_id,
                cancel_at_period_end=True,
            )
        except stripe.error.InvalidRequestError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except stripe.StripeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "detail": "Tu suscripción se cancelará al final del período actual.",
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "current_period_end": subscription.current_period_end,
            },
            status=status.HTTP_200_OK,
        )


class GithubRepoBranchesView(APIView):
    """List branches of a repository accessible via the GitHub App installation."""

    @extend_schema(
        summary="Listar branches de un repositorio",
        parameters=[
            {"name": "repo", "in": "query", "required": True, "schema": {"type": "string"}, "description": "owner/repo"},
        ],
        responses={200: dict, 400: dict},
        tags=["github-ide"],
    )
    def get(self, request):
        repo = request.query_params.get("repo", "").strip()
        if not repo:
            return Response({"detail": "El parámetro 'repo' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        token = self._resolve_token(request, repo)
        if isinstance(token, Response):
            return token

        url = f"{GITHUB_API_URL}/repos/{repo}/branches"
        resp = requests.get(url, headers=_github_headers(token), params={"per_page": 100}, timeout=20)
        if resp.status_code >= 400:
            return Response({"detail": "Error al obtener branches."}, status=status.HTTP_400_BAD_REQUEST)

        branches = [{"name": b["name"], "sha": b["commit"]["sha"]} for b in resp.json()]
        return Response({"branches": branches})

    @staticmethod
    def _resolve_token(request, repo: str) -> str | Response:
        """Try installation token first, fall back to user OAuth token."""
        if not _user_can_access_repo(request.user, repo):
            return Response({"detail": "No tienes acceso a este repositorio."}, status=status.HTTP_403_FORBIDDEN)
        org_login = repo.split("/")[0] if "/" in repo else repo
        installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()
        if installation:
            try:
                return _installation_access_token(installation.installation_id)
            except Exception:
                pass
        # Fall back to user's OAuth token
        connection = GithubConnection.objects.filter(user=request.user).first()
        if not connection:
            return Response({"detail": "No se encontró instalación ni conexión OAuth para este repositorio."}, status=status.HTTP_400_BAD_REQUEST)
        token = _get_valid_github_token(connection)
        if not token:
            return Response({"detail": "El token de GitHub del usuario expiró."}, status=status.HTTP_400_BAD_REQUEST)
        return token


class GithubCommitFilesView(APIView):
    """
    Commit one or more file changes to a GitHub repository branch in a single commit.
    Uses the Git Data API (blobs + tree + commit + ref update) to support multi-file
    atomic commits without individual file SHAs from the client.
    """

    @extend_schema(
        summary="Commit de archivos al repositorio",
        request={
            "application/json": {
                "type": "object",
                "required": ["repo", "branch", "message", "files"],
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "branch": {"type": "string", "description": "Branch de destino"},
                    "message": {"type": "string", "description": "Mensaje del commit"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["path", "content"],
                            "properties": {
                                "path": {"type": "string", "description": "Ruta del archivo (ej: src/main.py)"},
                                "content": {"type": "string", "description": "Contenido textual del archivo"},
                                "deleted": {"type": "boolean", "description": "Si es true, elimina el archivo"},
                            },
                        },
                    },
                },
            }
        },
        responses={201: dict, 400: dict},
        tags=["github-ide"],
    )
    def post(self, request):
        import base64 as b64

        repo = (request.data.get("repo") or "").strip()
        branch = (request.data.get("branch") or "").strip()
        message = (request.data.get("message") or "").strip()
        files = request.data.get("files")

        if not repo or not branch or not message or not files:
            return Response({"detail": "repo, branch, message y files son requeridos."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(files, list) or len(files) == 0:
            return Response({"detail": "'files' debe ser una lista no vacía."}, status=status.HTTP_400_BAD_REQUEST)
        if len(files) > 50:
            return Response({"detail": "Máximo 50 archivos por commit."}, status=status.HTTP_400_BAD_REQUEST)

        token = GithubRepoBranchesView._resolve_token(request, repo)
        if isinstance(token, Response):
            return token

        headers = _github_headers(token)

        # 1. Get current branch ref (latest commit SHA)
        ref_resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/git/refs/heads/{branch}",
            headers=headers, timeout=20,
        )
        if ref_resp.status_code == 404:
            return Response({"detail": f"Branch '{branch}' no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        if ref_resp.status_code >= 400:
            return Response({"detail": "Error al obtener ref."}, status=status.HTTP_400_BAD_REQUEST)

        latest_commit_sha = ref_resp.json()["object"]["sha"]

        # 2. Get the tree SHA of the latest commit
        commit_resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/git/commits/{latest_commit_sha}",
            headers=headers, timeout=20,
        )
        if commit_resp.status_code >= 400:
            return Response({"detail": "Error al obtener commit base."}, status=status.HTTP_400_BAD_REQUEST)

        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # 3. Create blobs for each file and build tree entries
        tree_entries = []
        for file_item in files:
            path = (file_item.get("path") or "").strip().lstrip("/")
            deleted = bool(file_item.get("deleted", False))
            if not path:
                return Response({"detail": "Cada archivo debe tener un 'path'."}, status=status.HTTP_400_BAD_REQUEST)

            if deleted:
                # Null sha signals deletion in GitHub's tree API
                tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue

            content = file_item.get("content")
            if content is None:
                return Response({"detail": f"El archivo '{path}' no tiene 'content'."}, status=status.HTTP_400_BAD_REQUEST)

            blob_resp = requests.post(
                f"{GITHUB_API_URL}/repos/{repo}/git/blobs",
                headers=headers,
                json={"content": b64.b64encode(content.encode("utf-8")).decode("ascii"), "encoding": "base64"},
                timeout=20,
            )
            if blob_resp.status_code >= 400:
                return Response({"detail": f"Error creando blob para '{path}'."}, status=status.HTTP_400_BAD_REQUEST)

            blob_sha = blob_resp.json()["sha"]
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

        # 4. Create a new tree
        new_tree_resp = requests.post(
            f"{GITHUB_API_URL}/repos/{repo}/git/trees",
            headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
            timeout=20,
        )
        if new_tree_resp.status_code >= 400:
            return Response({"detail": "Error creando árbol."}, status=status.HTTP_400_BAD_REQUEST)

        new_tree_sha = new_tree_resp.json()["sha"]

        # 5. Create the commit
        new_commit_resp = requests.post(
            f"{GITHUB_API_URL}/repos/{repo}/git/commits",
            headers=headers,
            json={"message": message, "tree": new_tree_sha, "parents": [latest_commit_sha]},
            timeout=20,
        )
        if new_commit_resp.status_code >= 400:
            return Response({"detail": "Error creando commit."}, status=status.HTTP_400_BAD_REQUEST)

        new_commit_sha = new_commit_resp.json()["sha"]
        commit_url = new_commit_resp.json().get("html_url") or f"https://github.com/{repo}/commit/{new_commit_sha}"

        # 6. Update the branch reference
        update_ref_resp = requests.patch(
            f"{GITHUB_API_URL}/repos/{repo}/git/refs/heads/{branch}",
            headers=headers,
            json={"sha": new_commit_sha, "force": False},
            timeout=20,
        )
        if update_ref_resp.status_code >= 400:
            return Response({"detail": "Error actualizando referencia."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "commit_sha": new_commit_sha,
                "commit_url": commit_url,
                "branch": branch,
                "files_changed": len(tree_entries),
            },
            status=status.HTTP_201_CREATED,
        )


class GithubChatProxyView(APIView):
    """Proxy chat requests from Django to the FastAPI service."""

    @extend_schema(responses={200: dict, 400: dict, 401: dict, 403: dict, 404: dict, 502: dict}, tags=["chat"])
    def post(self, request):
        fastapi_base_url = getattr(settings, "FASTAPI_CHAT_BASE_URL", "https://fast.yemoda.site").rstrip("/")
        upstream_url = f"{fastapi_base_url}/api/chat/"
        payload = request.data
        headers = {
            "Content-Type": "application/json",
            "Accept": request.headers.get("Accept", "application/json"),
        }

        # Preserve the caller's Authorization header if present so the upstream can
        # keep using the same user identity for audit/logging if needed.
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header:
            headers["Authorization"] = auth_header

        stream = bool(payload.get("stream")) if isinstance(payload, dict) else False

        try:
            if stream:
                upstream = requests.post(upstream_url, json=payload, headers=headers, stream=True, timeout=120)

                def event_stream():
                    try:
                        for chunk in upstream.iter_content(chunk_size=4096):
                            if chunk:
                                yield chunk
                    finally:
                        upstream.close()

                response = StreamingHttpResponse(event_stream(), content_type=upstream.headers.get("Content-Type", "text/event-stream"))
                response.status_code = upstream.status_code
                for header_name in ("Cache-Control", "X-Accel-Buffering"):
                    if upstream.headers.get(header_name):
                        response[header_name] = upstream.headers[header_name]
                return response

            upstream = requests.post(upstream_url, json=payload, headers=headers, timeout=120)
        except requests.RequestException as exc:
            return JsonResponse(
                {"detail": "No se pudo conectar con el servicio de IA de FastAPI.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        content_type = upstream.headers.get("Content-Type", "application/json")
        if upstream.status_code >= 400:
            return HttpResponse(upstream.content, status=upstream.status_code, content_type=content_type)

        return HttpResponse(upstream.content, status=upstream.status_code, content_type=content_type)


class GithubAppDebugView(APIView):
    """Debug endpoint for GitHub App private key — admin only."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        pk = settings.GITHUB_APP_PRIVATE_KEY or ""
        # Only expose booleans about whether the App is configured — never key material,
        # line contents, or stack traces (admin-only, but still no secret fragments).
        result = {
            "github_app_id_configured": bool(settings.GITHUB_APP_ID),
            "private_key_configured": bool(pk),
            "has_begin_header": "-----BEGIN RSA PRIVATE KEY-----" in pk or "-----BEGIN PRIVATE KEY-----" in pk,
            "has_end_footer": "-----END RSA PRIVATE KEY-----" in pk or "-----END PRIVATE KEY-----" in pk,
            "jwt_ok": False,
        }
        try:
            _github_app_jwt()
            result["jwt_ok"] = True
        except Exception:
            result["jwt_ok"] = False
        return Response(result)


class GithubConnectionStatusView(APIView):
    @extend_schema(
        summary="Estado de conexión con GitHub",
        description=(
            "Devuelve si el usuario autenticado tiene una cuenta de GitHub vinculada. "
            "El frontend usa esto para decidir si mostrar el botón 'Conectar con GitHub'. "
            "Si el token está expirado pero el refresh token es válido, lo renueva automáticamente."
        ),
        responses={
            200: {
                "type": "object",
                "properties": {
                    "connected": {"type": "boolean"},
                    "github_login": {"type": "string", "nullable": True},
                    "reason": {"type": "string", "nullable": True, "description": "Solo presente si connected=false. Valor posible: 'token_expired'"},
                },
            }
        },
        tags=["github-app"],
    )
    def get(self, request):
        user = request.user
        connection = GithubConnection.objects.filter(user=user).first()
        if not connection:
            return Response({"connected": False, "github_login": None}, status=status.HTTP_200_OK)

        now = datetime.now(timezone.utc)
        token_expired = bool(connection.token_expires_at and connection.token_expires_at <= now)
        refresh_expired = bool(
            connection.refresh_token_expires_at and connection.refresh_token_expires_at <= now
        ) if connection.refresh_token else True

        if token_expired:
            if refresh_expired:
                return Response(
                    {"connected": False, "github_login": connection.github_login, "reason": "token_expired"},
                    status=status.HTTP_200_OK,
                )
            refreshed = _refresh_github_token(connection)
            if not refreshed:
                return Response(
                    {"connected": False, "github_login": connection.github_login, "reason": "token_expired"},
                    status=status.HTTP_200_OK,
                )

        return Response(
            {"connected": True, "github_login": connection.github_login},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Desvincular cuenta de GitHub",
        description=(
            "Elimina la conexión de GitHub del usuario autenticado. "
            "No requiere body. El usuario se identifica por el JWT del header Authorization. "
            "Después de esta operación, el usuario deberá volver a conectar su cuenta de GitHub."
        ),
        responses={
            200: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "example": "Cuenta de GitHub desvinculada correctamente."}
                },
            },
            404: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "example": "No había ninguna cuenta de GitHub vinculada."}
                },
            },
        },
        tags=["github-app"],
    )
    def delete(self, request):
        """Desvincula la cuenta de GitHub del usuario autenticado."""
        user = request.user
        deleted, _ = GithubConnection.objects.filter(user=user).delete()
        if deleted:
            return Response({"detail": "Cuenta de GitHub desvinculada correctamente."}, status=status.HTTP_200_OK)
        return Response({"detail": "No había ninguna cuenta de GitHub vinculada."}, status=status.HTTP_404_NOT_FOUND)


MAX_REPOS_PER_PROJECT = 4


class ProjectRepoView(APIView):
    @extend_schema(responses={200: ProjectRepoSerializer(many=True)}, tags=["projects"])
    def get(self, request, project_id):
        """Lista los repositorios vinculados a un proyecto."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        is_member = (
            project.created_by == request.user
            or ProjectMember.objects.filter(project=project, user=request.user).exists()
        )
        if not is_member:
            return Response({"detail": "No tienes acceso a este proyecto."}, status=status.HTTP_403_FORBIDDEN)

        repos = ProjectRepo.objects.filter(project=project).order_by("created_at")
        return Response(ProjectRepoSerializer(repos, many=True).data)

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"repo_full_name": {"type": "string"}}, "required": ["repo_full_name"]}},
        responses={201: ProjectRepoSerializer, 400: dict, 403: dict, 404: dict},
        tags=["projects"],
    )
    def post(self, request, project_id):
        """Vincula un repositorio a un proyecto (máximo 4)."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if project.created_by != request.user:
            return Response({"detail": "Solo el creador del proyecto puede vincular repositorios."}, status=status.HTTP_403_FORBIDDEN)

        repo_full_name = (request.data.get("repo_full_name") or "").strip()
        if not repo_full_name:
            return Response({"detail": "repo_full_name es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        current_count = ProjectRepo.objects.filter(project=project).count()
        if current_count >= MAX_REPOS_PER_PROJECT:
            return Response(
                {"detail": f"El proyecto ya tiene el máximo de {MAX_REPOS_PER_PROJECT} repositorios vinculados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repo, created = ProjectRepo.objects.get_or_create(project=project, repo_full_name=repo_full_name)
        if not created:
            return Response({"detail": "Este repositorio ya está vinculado al proyecto."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ProjectRepoSerializer(repo).data, status=status.HTTP_201_CREATED)


class ProjectRepoDetailView(APIView):
    @extend_schema(responses={204: None, 403: dict, 404: dict}, tags=["projects"])
    def delete(self, request, project_id, repo_id):
        """Desvincula un repositorio de un proyecto."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if project.created_by != request.user:
            return Response({"detail": "Solo el creador del proyecto puede desvincular repositorios."}, status=status.HTTP_403_FORBIDDEN)

        repo = ProjectRepo.objects.filter(pk=repo_id, project=project).first()
        if not repo:
            return Response({"detail": "Repositorio no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        repo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

