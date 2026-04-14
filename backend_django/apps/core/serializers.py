from rest_framework import serializers

from .models import (
    ActivityLog,
    Board,
    GithubPushEvent,
    Project,
    ProjectMember,
    Role,
    SystemRole,
    Task,
    TaskComment,
    TaskPriority,
    TaskStatus,
    TaskWarning,
    UserAccount,
)


class SystemRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemRole
        fields = "__all__"


class UserAccountSerializer(serializers.ModelSerializer):
    password_hash = serializers.CharField(write_only=True, required=False)
    system_role_name = serializers.CharField(source="system_role.name", read_only=True)

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


class GithubPushEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = GithubPushEvent
        fields = "__all__"


class TaskWarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskWarning
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


class GithubOauthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()


class GithubCreateRepoSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    project_id = serializers.IntegerField(required=False, min_value=1, help_text="ID del proyecto al que se vinculará el repositorio.")
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    private = serializers.BooleanField(default=True)
    auto_init = serializers.BooleanField(default=True)
    owner_type = serializers.ChoiceField(choices=["user", "org"], default="user")
    owner = serializers.CharField(required=False, allow_blank=True)
    installation_id = serializers.IntegerField(required=False, min_value=1)
    webhook_url = serializers.URLField(required=False)


class GithubAppLinkInstallationSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    installation_id = serializers.IntegerField(min_value=1)
