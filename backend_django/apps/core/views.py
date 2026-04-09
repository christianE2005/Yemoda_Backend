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
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ActivityLog,
    Board,
    GithubAppInstallation,
    GithubConnection,
    Project,
    ProjectMember,
    Role,
    Task,
    TaskComment,
    TaskPriority,
    TaskStatus,
    UserAccount,
)
from .serializers import (
    ActivityLogSerializer,
    BoardSerializer,
    GithubAppLinkInstallationSerializer,
    GithubCreateRepoSerializer,
    GithubOauthCallbackSerializer,
    LoginSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    RefreshSerializer,
    RegisterSerializer,
    RoleSerializer,
    TaskCommentSerializer,
    TaskPrioritySerializer,
    TaskSerializer,
    TaskStatusSerializer,
    UserAccountSerializer,
)

GITHUB_API_URL = "https://api.github.com"


def _issue_tokens(user: UserAccount) -> dict:
    access_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    access_payload = {
        "sub": str(user.id_user),
        "email": user.email,
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

    membership_response = requests.get(
        f"{GITHUB_API_URL}/user/memberships/orgs/{org_login}",
        headers=_github_headers(github_connection.access_token),
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


class UserAccountViewSet(viewsets.ModelViewSet):
    queryset = UserAccount.objects.all()
    serializer_class = UserAccountSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer


class ProjectMemberViewSet(viewsets.ModelViewSet):
    queryset = ProjectMember.objects.all()
    serializer_class = ProjectMemberSerializer


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer


class TaskStatusViewSet(viewsets.ModelViewSet):
    queryset = TaskStatus.objects.all()
    serializer_class = TaskStatusSerializer


class TaskPriorityViewSet(viewsets.ModelViewSet):
    queryset = TaskPriority.objects.all()
    serializer_class = TaskPrioritySerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.all()
    serializer_class = TaskCommentSerializer


class ActivityLogViewSet(viewsets.ModelViewSet):
    queryset = ActivityLog.objects.all()
    serializer_class = ActivityLogSerializer


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

        if UserAccount.objects.filter(email=email).exists():
            return Response({"detail": "El correo ya esta registrado."}, status=status.HTTP_400_BAD_REQUEST)

        user = UserAccount.objects.create(
            email=email,
            username=username,
            password_hash=make_password(password),
        )
        return Response(UserAccountSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: dict, 401: dict},
        tags=["auth"],
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
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict, 500: dict}, tags=["github-app"])
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

        state = secrets.token_urlsafe(24)
        request.session["github_app_oauth_state"] = state
        params = {
            "client_id": settings.GITHUB_APP_CLIENT_ID,
            "redirect_uri": settings.GITHUB_APP_OAUTH_CALLBACK_URL,
            "state": state,
        }
        authorize_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        return Response({"authorize_url": authorize_url, "state": state}, status=status.HTTP_200_OK)


class GithubAppOauthCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GithubOauthCallbackSerializer, responses={200: dict, 400: dict, 500: dict}, tags=["github-app"])
    def _complete_oauth(self, request, code: str, state: str) -> tuple[dict | None, str | None, int]:
        session_state = request.session.get("github_app_oauth_state")
        if not session_state or not secrets.compare_digest(state, session_state):
            return None, "OAuth state invalido.", status.HTTP_400_BAD_REQUEST
        request.session.pop("github_app_oauth_state", None)

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

        access_token = token_response.json().get("access_token")
        if not access_token:
            return None, "GitHub no devolvio access_token.", status.HTTP_400_BAD_REQUEST

        user_response = requests.get(f"{GITHUB_API_URL}/user", headers=_github_headers(access_token), timeout=20)
        if user_response.status_code >= 400:
            return None, "No se pudo obtener usuario de GitHub.", status.HTTP_400_BAD_REQUEST
        github_user = user_response.json()

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
            email = github_user.get("email") or f"{github_user['login']}@users.noreply.github.com"

        username = github_user.get("login") or email.split("@")[0]
        user = UserAccount.objects.filter(email=email).first()
        if not user:
            user = UserAccount.objects.create(
                email=email,
                username=username,
                password_hash=make_password(None),
            )
        elif user.username != username:
            user.username = username
            user.save(update_fields=["username"])

        GithubConnection.objects.update_or_create(
            user=user,
            defaults={
                "github_user_id": github_user["id"],
                "github_login": github_user["login"],
                "access_token": access_token,
            },
        )

        tokens = _issue_tokens(user)
        return (
            {**tokens, "user": UserAccountSerializer(user).data, "github_login": github_user["login"]},
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
            auth_headers = _github_headers(github_connection.access_token)
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
            try:
                token = _installation_access_token(resolved_installation_id)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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

        return Response(
            {
                "repository": (payload.get("repository") or {}).get("full_name"),
                "ref": payload.get("ref"),
                "pusher": (payload.get("pusher") or {}).get("name"),
                "installation_id": installation_id,
                "total_commits": len(commits),
                "commits": commit_summaries,
            },
            status=status.HTTP_200_OK,
        )
