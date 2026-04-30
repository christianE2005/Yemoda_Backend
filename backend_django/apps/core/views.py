from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpResponse
from django.db import models
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from .authentication import IsAdminUser
from rest_framework.response import Response
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
    SystemRole,
    Tag,
    Task,
    TaskAssignment,
    TaskComment,
    TaskPriority,
    TaskPushMatch,
    TaskStatus,
    TaskWarning,
    UserAccount,
)
from .serializers import (
    ActivityLogSerializer,
    BoardColumnSerializer,
    BoardSerializer,
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
    RoleSerializer,
    SprintSerializer,
    SystemRoleSerializer,
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
_GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _issue_tokens(user: UserAccount) -> dict:
    access_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    access_payload = {
        "sub": str(user.id_user),
        "email": user.email,
        "is_admin": user.is_admin,
        "system_role_id": user.system_role_id,
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

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_create(self, serializer):
        """Admin creates users with hashed passwords"""
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
    authentication_classes = []
    permission_classes = [AllowAny]


class SystemRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """System-level roles (Admin, User). Read-only — managed via migrations/DB."""
    queryset = SystemRole.objects.all()
    serializer_class = SystemRoleSerializer
    authentication_classes = []
    permission_classes = [AllowAny]


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
        """Filter boards by ?project= query param when provided."""
        qs = Board.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs


class BoardColumnViewSet(viewsets.ModelViewSet):
    queryset = BoardColumn.objects.all()
    serializer_class = BoardColumnSerializer

    def get_queryset(self):
        """Filter columns by ?board= query param when provided."""
        qs = BoardColumn.objects.all()
        board_id = self.request.query_params.get('board')
        if board_id is not None:
            qs = qs.filter(board_id=board_id)
        return qs


class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all()
    serializer_class = SprintSerializer

    def get_queryset(self):
        """Filter sprints by ?project= or ?status= query params."""
        qs = Sprint.objects.all()
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
        """Filter milestones by ?project= query param."""
        qs = Milestone.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

    def get_queryset(self):
        """Filter tags by ?project= query param."""
        qs = Tag.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id is not None:
            qs = qs.filter(project_id=project_id)
        return qs


class TaskStatusViewSet(viewsets.ModelViewSet):
    queryset = TaskStatus.objects.all()
    serializer_class = TaskStatusSerializer


class TaskPriorityViewSet(viewsets.ModelViewSet):
    queryset = TaskPriority.objects.all()
    serializer_class = TaskPrioritySerializer


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

        return qs.distinct()


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.all()
    serializer_class = TaskCommentSerializer

    def get_queryset(self):
        """Filter comments by ?task= query param when provided."""
        qs = TaskComment.objects.all()
        task_id = self.request.query_params.get('task')
        if task_id is not None:
            qs = qs.filter(task_id=task_id)
        return qs


class TaskAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAssignment.objects.all()
    serializer_class = TaskAssignmentSerializer

    def get_queryset(self):
        """Filter assignments by ?task= or ?user= query params."""
        qs = TaskAssignment.objects.all()
        task_id = self.request.query_params.get('task')
        user_id = self.request.query_params.get('user')
        
        if task_id is not None:
            qs = qs.filter(task_id=task_id)
        if user_id is not None:
            qs = qs.filter(assigned_to_id=user_id)
        
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
        system_role_id = serializer.validated_data.get("system_role_id")

        if UserAccount.objects.filter(email=email).exists():
            return Response({"detail": "El correo ya esta registrado."}, status=status.HTTP_400_BAD_REQUEST)

        system_role = None
        if system_role_id:
            system_role = SystemRole.objects.filter(pk=system_role_id).first()
            if not system_role:
                return Response({"detail": "El rol indicado no existe."}, status=status.HTTP_400_BAD_REQUEST)

        user = UserAccount.objects.create(
            email=email,
            username=username,
            password_hash=make_password(password),
            system_role=system_role,
        )
        return Response(UserAccountSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

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

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": UserAccountSerializer(user).data}, status=status.HTTP_200_OK)


class RefreshView(APIView):
    permission_classes = [AllowAny]

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
            "scope": "read:org",
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

        # Verify the user belongs to an org that has the GitHub App installed
        orgs_response = requests.get(
            f"{GITHUB_API_URL}/user/orgs",
            headers=_github_headers(access_token),
            timeout=20,
        )
        if orgs_response.status_code >= 400:
            return None, "No se pudieron obtener las organizaciones del usuario.", status.HTTP_400_BAD_REQUEST

        user_orgs = orgs_response.json()
        user_org_logins = {org["login"].lower() for org in user_orgs}
        user_org_by_login = {org["login"].lower(): org["login"] for org in user_orgs}

        if not user_org_logins:
            return (
                None,
                "No perteneces a ninguna organización que tenga la aplicación instalada. "
                "Pide a un administrador que instale la app en tu organización.",
                status.HTTP_403_FORBIDDEN,
            )

        # 1. Check local DB first (fast path)
        installed_orgs_db = set(
            GithubAppInstallation.objects.filter(
                account_login__iregex=r"^(" + "|".join(user_org_logins) + r")$",
                account_type="Organization",
            ).values_list("account_login", flat=True)
        )
        matching_orgs = user_org_logins & {o.lower() for o in installed_orgs_db}

        # 2. Fallback: verify via GitHub API for orgs not yet in DB
        if not matching_orgs:
            try:
                app_headers = _github_app_headers()
                for org_lower, org_login in user_org_by_login.items():
                    inst_resp = requests.get(
                        f"{GITHUB_API_URL}/orgs/{org_login}/installation",
                        headers=app_headers,
                        timeout=20,
                    )
                    if inst_resp.status_code == 200:
                        inst_data = inst_resp.json()
                        inst_id = inst_data.get("id")
                        account = (inst_data.get("account") or {})
                        if inst_id:
                            GithubAppInstallation.objects.update_or_create(
                                installation_id=inst_id,
                                defaults={
                                    "account_login": account.get("login", org_login),
                                    "account_type": account.get("type", "Organization"),
                                },
                            )
                            matching_orgs.add(org_lower)
            except Exception:
                pass

        if not matching_orgs:
            return (
                None,
                "No perteneces a ninguna organización que tenga la aplicación instalada. "
                "Pide a un administrador que instale la app en tu organización.",
                status.HTTP_403_FORBIDDEN,
            )

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
                "authorized_orgs": list(matching_orgs),
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


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


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

