from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpResponse, HttpResponseRedirect
from django.db import models
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from .authentication import IsAdminUser
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
    Role,
    Sprint,
    Tag,
    Task,
    TaskAssignment,
    TaskComment,
    TaskPriority,
    TaskPushMatch,
    TaskStatus,
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
    TaskWarningSerializer,
    UserAccountSerializer,
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
    access_payload = {
        "sub": str(user.id_user),
        "email": user.email,
        "is_admin": user.is_admin,
        "type": "access",
        "exp": access_expires_at,
    }
    refresh_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_REFRESH_EXPIRE_MINUTES)
    refresh_payload = {
        "sub": str(user.id_user),
        "email": user.email,
        "type": "refresh",
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


def _build_signed_oauth_state() -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "nonce": secrets.token_urlsafe(24),
        "exp": int(expires_at.timestamp()),
        "purpose": "github_app_oauth",
    }
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
        },
        timeout=10,
    )


def _validate_signed_oauth_state(state: str) -> bool:
    try:
        payload = jwt.decode(state, settings.GITHUB_APP_STATE_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False
    return payload.get("purpose") == "github_app_oauth"


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
    queryset = UserAccount.objects.all()
    serializer_class = UserAccountSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_admin:
            return UserAccount.objects.all()
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
        return UserAccount.objects.filter(
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
            from rest_framework.exceptions import PermissionDenied
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
        import traceback
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"error": str(e), "detail": traceback.format_exc()},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user, status=Project.PLANNING)
        try:
            ProjectMember.objects.get_or_create(
                project=project,
                user=self.request.user,
                defaults={"role": None},
            )
        except Exception:
            pass


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            authentication_classes = []
            return [AllowAny()]
        return [IsAdminUser()]

    def get_authenticators(self):
        if self.action in ('list', 'retrieve'):
            return []
        return super().get_authenticators()


class ProjectMemberViewSet(viewsets.ModelViewSet):
    queryset = ProjectMember.objects.all()
    serializer_class = ProjectMemberSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        user = serializer.validated_data.get('user')
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
        """Añade un usuario a un proyecto."""
        project = Project.objects.filter(pk=project_id).first()
        if not project:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if project.created_by != request.user:
            user_projects = Project.objects.filter(members__user=request.user).values_list('id_project', flat=True)
            if project_id not in user_projects:
                return Response({"detail": "No tienes acceso a este proyecto."}, status=status.HTTP_403_FORBIDDEN)

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

        member = ProjectMember.objects.create(project=project, user=user, role=role)

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
        instance = serializer.save()
        self._enforce_single_review(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._enforce_single_review(instance)


class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all()
    serializer_class = SprintSerializer

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


class MilestoneViewSet(viewsets.ModelViewSet):
    queryset = Milestone.objects.all()
    serializer_class = MilestoneSerializer

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

        # ?backlog=true returns only tasks with no sprint assigned (backlog)
        backlog = self.request.query_params.get('backlog')
        if backlog is not None and backlog.lower() == 'true':
            qs = qs.filter(sprint__isnull=True)

        tag_id = self.request.query_params.get('tag')
        if tag_id is not None:
            qs = qs.filter(tags__id_tag=tag_id)

        return qs.distinct().prefetch_related('assignments__assigned_to', 'tags')


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


class ActivityLogViewSet(viewsets.ModelViewSet):
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
            return Response(
                {"detail": "Por favor verifica tu correo electrónico antes de iniciar sesión.", "code": "email_not_verified"},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        request.user.password_hash = make_password(new_password)
        request.user.save(update_fields=["password_hash"])
        return Response({"detail": "Contraseña actualizada correctamente."}, status=status.HTTP_200_OK)


class VerifyEmailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={302: None},
        tags=["auth"],
        summary="Verificar correo electrónico",
        description="El usuario llega aquí desde el link del correo. Verifica el token y redirige al frontend.",
    )
    def get(self, request):
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


def _build_google_oauth_state() -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "nonce": secrets.token_urlsafe(24),
        "exp": int(expires_at.timestamp()),
        "purpose": "google_oauth",
    }
    return jwt.encode(payload, settings.GOOGLE_STATE_SECRET, algorithm="HS256")


def _validate_google_oauth_state(state: str) -> bool:
    try:
        payload = jwt.decode(state, settings.GOOGLE_STATE_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return False
    return payload.get("purpose") == "google_oauth"


class GoogleOauthStartView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: dict, 503: dict},
        tags=["auth"],
        summary="Iniciar flujo OAuth con Google",
        description="Devuelve la URL de autorización de Google. El frontend redirige al usuario a esa URL.",
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
        return Response({"auth_url": auth_url, "state": state})


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
        frontend_redirect = settings.GOOGLE_AUTH_FRONTEND_REDIRECT
        error = request.query_params.get("error")
        code = request.query_params.get("code")
        state = request.query_params.get("state", "")

        if error or not code:
            return HttpResponseRedirect(f"{frontend_redirect}?error={error or 'no_code'}")

        if not _validate_google_oauth_state(state):
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
        name = userinfo.get("name") or email.split("@")[0]
        user, _ = UserAccount.objects.get_or_create(
            email=email,
            defaults={
                "username": name,
                "password_hash": make_password(None),  # unusable — Google-only login
                "is_email_verified": True,
            },
        )

        tokens = _issue_tokens(user)
        redirect_url = (
            f"{frontend_redirect}"
            f"?access_token={tokens['access_token']}"
            f"&refresh_token={tokens['refresh_token']}"
            f"&expires_at={tokens['expires_at']}"
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

        state = _build_signed_oauth_state()
        params = {
            "client_id": settings.GITHUB_APP_CLIENT_ID,
            "redirect_uri": settings.GITHUB_APP_OAUTH_CALLBACK_URL,
            "state": state,
            "scope": "repo,read:user,read:org",
        }
        authorize_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        return Response({"authorize_url": authorize_url, "state": state}, status=status.HTTP_200_OK)


class GithubAppOauthCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GithubOauthCallbackSerializer, responses={200: dict, 400: dict, 401: dict, 500: dict}, tags=["github-app"])
    def _complete_oauth(self, request, code: str, state: str) -> tuple[dict | None, str | None, int]:
        if not _validate_signed_oauth_state(state):
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
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return HttpResponse("OAuth failed: code/state missing", status=400, content_type="text/plain")

        payload, error, status_code = self._complete_oauth(request, code=code, state=state)
        if error:
            return HttpResponse(f"OAuth failed: {error}", status=status_code, content_type="text/plain")
        return HttpResponse("OAuth completed successfully", status=200, content_type="text/plain")

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
        user_id = serializer.validated_data["user_id"]
        installation_id = serializer.validated_data["installation_id"]

        user = UserAccount.objects.filter(id_user=user_id).first()
        if not user:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

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
                {"detail": "No se pudo consultar la instalacion.", "github_response": installation_response.text},
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

        user = UserAccount.objects.filter(id_user=data["user_id"]).first()
        if not user:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

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
            return Response(
                {"detail": "No se pudo crear el repositorio.", "github_response": repo_response.text},
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

        webhook_url = data.get("webhook_url") or settings.GITHUB_APP_WEBHOOK_TARGET_URL
        if not webhook_url:
            return Response(
                {
                    "detail": "Repositorio creado, pero falta webhook_url. Configura GITHUB_APP_WEBHOOK_TARGET_URL o envia webhook_url.",
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
                    "github_response": hooks_response.text,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response({"repository": repo, "webhook": hooks_response.json()}, status=status.HTTP_201_CREATED)


class GithubPushWebhookView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_webhook"

    @extend_schema(request=dict, responses={200: dict, 400: dict, 401: dict}, tags=["github-app"])
    def post(self, request):
        payload_bytes = request.body
        signature = request.headers.get("X-Hub-Signature-256", "")

        if settings.GITHUB_APP_WEBHOOK_SECRET:
            expected = "sha256=" + hmac.new(
                settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8"),
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

        project = Project.objects.filter(repos__repo_full_name__iexact=repo_full_name).first()
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
        Retorna los push events recibidos.
        Filtros opcionales: ?project_id=1  o  ?repo=owner/repo
        """
        qs = GithubPushEvent.objects.all()
        project_id = request.query_params.get("project_id")
        repo = request.query_params.get("repo")
        if project_id:
            qs = qs.filter(project_id=project_id)
        if repo:
            qs = qs.filter(repo_full_name__iexact=repo)
        qs = qs[:50]
        serializer = GithubPushEventSerializer(qs, many=True)
        return Response(serializer.data)


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
                {"detail": "No se pudo obtener el diff.", "github_response": diff_response.text},
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

        org_login = repo.split("/")[0] if "/" in repo else repo
        installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()
        if not installation:
            return Response(
                {"detail": f"No se encontró instalación de GitHub App para '{org_login}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = _installation_access_token(installation.installation_id)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({"detail": "Error al obtener contenidos.", "github_response": response.text}, status=status.HTTP_400_BAD_REQUEST)

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
        task = Task.objects.filter(pk=task_id).first()
        if not task:
            return Response({"detail": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

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
                {"detail": "Error enviando el review a GitHub.", "github_response": resp.text},
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
                {"detail": "Error publicando el comentario en GitHub.", "github_response": resp.text},
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
        repo_full_name = (project_repo.repo_full_name if project_repo else None) or project.github_repo_full_name
        if not repo_full_name:
            return Response(
                {"detail": "El proyecto no tiene un repositorio de GitHub vinculado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org_login = repo_full_name.split("/")[0]
        installation = GithubAppInstallation.objects.filter(account_login__iexact=org_login).first()
        if not installation:
            return Response(
                {"detail": f"No se encontró instalación de GitHub App para '{org_login}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = _installation_access_token(installation.installation_id)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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
                {"detail": "Error consultando la rama base en GitHub.", "github_response": ref_resp.text},
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
                {"detail": "Error creando la rama en GitHub.", "github_response": create_resp.text},
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


class GithubAppDebugView(APIView):
    """Temporary debug endpoint — remove after fixing private key issue."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        import traceback
        result = {
            "github_app_id": settings.GITHUB_APP_ID or "(not set)",
            "private_key_length": len(settings.GITHUB_APP_PRIVATE_KEY),
            "private_key_starts_with": settings.GITHUB_APP_PRIVATE_KEY[:40] if settings.GITHUB_APP_PRIVATE_KEY else "(empty)",
            "jwt_ok": False,
            "jwt_error": None,
        }
        try:
            _github_app_jwt()
            result["jwt_ok"] = True
        except Exception as exc:
            result["jwt_error"] = str(exc)
            result["traceback"] = traceback.format_exc()
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

