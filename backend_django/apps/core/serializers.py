from rest_framework import serializers

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


class UserAccountSerializer(serializers.ModelSerializer):
    password_hash = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = UserAccount
        fields = "__all__"


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"


class ProjectMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = "__all__"


class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = "__all__"


class TaskStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStatus
        fields = "__all__"


class TaskPrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPriority
        fields = "__all__"


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = "__all__"


class TaskCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = "__all__"


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = "__all__"


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=8)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(write_only=True)
