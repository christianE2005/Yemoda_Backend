from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ActivityLog,
    Board,
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

        return Response(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_at": access_expires_at.isoformat(),
                "user": UserAccountSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class RefreshView(APIView):
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

        access_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        access_payload = {
            "sub": str(user.id_user),
            "email": user.email,
            "type": "access",
            "exp": access_expires_at,
        }
        access_token = jwt.encode(access_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        return Response(
            {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_at": access_expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
