import re

from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from drf_spectacular.utils import extend_schema_field

from .models import (
    ActivityLog,
    Board,
    BoardColumn,
    GithubPushEvent,
    GithubRepo,
    Hackathon,
    HackathonSubmission,
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
    TaskAIReviewResult,
    TaskPushMatch,
    TaskStatus,
    TaskWarning,
    UserAccount,
)

# Fixed scoring categories for the Hackathon Robustness Score and the default rubric weights.
HACKATHON_CATEGORIES = (
    "security",
    "performance",
    "robustness",
    "correctness",
    "maintainability",
    "tdd",
)
DEFAULT_HACKATHON_RUBRIC = {
    "security": 30,
    "performance": 10,
    "robustness": 25,
    "correctness": 20,
    "maintainability": 15,
    "tdd": 0,
}


class UserAccountSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    is_admin = serializers.BooleanField(read_only=True)
    is_premium = serializers.BooleanField(read_only=True)
    subscription_plan = serializers.CharField(read_only=True, allow_null=True)
    is_email_verified = serializers.BooleanField(read_only=True)
    github_connected = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()

    def get_github_connected(self, obj):
        return hasattr(obj, 'github_connection')

    def get_github_login(self, obj):
        conn = getattr(obj, 'github_connection', None)
        return conn.github_login if conn else None

    class Meta:
        model = UserAccount
        fields = ["id_user", "email", "username", "password", "is_admin", "is_premium", "subscription_plan", "is_email_verified", "created_at", "github_connected", "github_login"]

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("El nickname no puede estar vacío.")

        qs = UserAccount.objects.filter(username__iexact=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este nickname ya está en uso.")
        return username

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = UserAccount(**validated_data)
        if password:
            user.password_hash = make_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        # Profile updates cannot change email.
        validated_data.pop("email", None)
        if password:
            instance.password_hash = make_password(password)
        return super().update(instance, validated_data)


class ProjectSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Project
        fields = "__all__"
        # `plan` and `stripe_subscription_id` are entitlement/billing fields that may ONLY be
        # changed server-side by the Stripe webhook — never by a client request body (otherwise
        # any user could POST plan="pro" and get paid AI quotas for free).
        read_only_fields = ["id_project", "plan", "stripe_subscription_id", "created_at"]


class ProjectRepoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectRepo
        fields = "__all__"
        read_only_fields = ["id_project_repo", "created_at"]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"


class ProjectRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectRole
        fields = "__all__"
        read_only_fields = ("id_project_role", "is_admin_role", "is_system", "created_at")

    def validate(self, attrs):
        # max_move_column must belong to a board of the same project.
        project = attrs.get("project") or (self.instance.project if self.instance else None)
        column = attrs.get("max_move_column")
        if column is not None and project is not None and column.board.project_id != project.id_project:
            raise serializers.ValidationError(
                {"max_move_column": "La columna debe pertenecer a un tablero de este proyecto."}
            )
        return attrs


class ProjectMemberSerializer(serializers.ModelSerializer):
    # Read-only details of the assigned per-project role, for display.
    project_role_name = serializers.CharField(source="project_role.name", read_only=True, allow_null=True)

    class Meta:
        model = ProjectMember
        fields = "__all__"
        read_only_fields = ("id", "joined_at")


class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = "__all__"

    def validate_custom_instructions(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError(
                "Custom instructions cannot exceed 1000 characters."
            )
        return value


class BoardColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoardColumn
        fields = "__all__"


class SprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sprint
        fields = "__all__"


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = "__all__"


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = "__all__"


class TaskStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStatus
        fields = "__all__"


class TaskPrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPriority
        fields = "__all__"


class TaskAssignedUserSerializer(serializers.Serializer):
    id_user = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    id_assignment = serializers.IntegerField()


def _sum_leaf_points(task, _depth=0):
    """
    Sum story_points across the leaf descendants of a task.

    Only leaf tasks (no subtasks) carry real points; a parent rolls up the points
    of its leaves. Returns the task's own story_points when it has no subtasks.
    The depth guard protects against accidentally cyclic data.
    """
    if _depth > 20:
        return 0
    subtasks = list(task.subtasks.all())
    if not subtasks:
        return task.story_points or 0
    return sum(_sum_leaf_points(s, _depth + 1) for s in subtasks)


class SubtaskProgressSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    percent = serializers.IntegerField()


class TaskSerializer(serializers.ModelSerializer):
    assigned_users = serializers.SerializerMethodField()
    subtask_progress = serializers.SerializerMethodField()
    rolled_up_points = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = "__all__"

    @extend_schema_field(TaskAssignedUserSerializer(many=True))
    def get_assigned_users(self, obj):
        """Return list of assigned users with their details"""
        assignments = obj.assignments.all()
        return [
            {
                "id_user": assignment.assigned_to.id_user,
                "email": assignment.assigned_to.email,
                "username": assignment.assigned_to.username,
                "id_assignment": assignment.id_assignment,
            }
            for assignment in assignments
        ]

    @extend_schema_field(SubtaskProgressSerializer)
    def get_subtask_progress(self, obj):
        """Completion progress over direct subtasks (immediate children)."""
        subtasks = list(obj.subtasks.all())
        total = len(subtasks)
        if total == 0:
            return {"total": 0, "completed": 0, "percent": 0}
        completed = sum(1 for s in subtasks if s.completed_at is not None)
        return {
            "total": total,
            "completed": completed,
            "percent": round(completed * 100 / total),
        }

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_rolled_up_points(self, obj):
        """
        Points for a task. Only leaf tasks carry their own points; a parent's
        value is the sum of its leaf descendants' story_points. Returns the task's
        own story_points when it has no subtasks.
        """
        return _sum_leaf_points(obj)

    def validate_story_points(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("story_points debe ser al menos 1.")
        return value

    def validate(self, attrs):
        project = attrs.get('project') or (self.instance.project if self.instance else None)

        scrum_number = attrs.get('scrum_number')
        if scrum_number is not None and project is not None:
            qs = Task.objects.filter(project=project, scrum_number=scrum_number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"scrum_number": "Ya existe una tarea con ese número en este proyecto."}
                )

        # ── Parent / subtask validation ──────────────────────────────────────
        parent = attrs.get('parent', serializers.empty)
        if parent is not serializers.empty and parent is not None:
            if self.instance and parent.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"parent": "Una tarea no puede ser su propia subtarea."}
                )
            if project is not None and parent.project_id != project.id_project:
                raise serializers.ValidationError(
                    {"parent": "La tarea padre debe pertenecer al mismo proyecto."}
                )
            # Prevent cycles: the chosen parent cannot be a descendant of this task.
            if self.instance:
                ancestor = parent
                seen = set()
                while ancestor is not None and ancestor.pk not in seen:
                    if ancestor.pk == self.instance.pk:
                        raise serializers.ValidationError(
                            {"parent": "No se puede asignar como padre a una de sus propias subtareas (ciclo)."}
                        )
                    seen.add(ancestor.pk)
                    ancestor = ancestor.parent

        # ── Completion blocking: a parent cannot be MOVED to a final column while
        #    it still has incomplete subtasks. Only enforced when board_column is
        #    explicitly provided (a transition), so unrelated edits on a task that
        #    already sits in a final column are not blocked. ──────────────────────
        board_column = attrs.get('board_column', serializers.empty)
        moving_to_final = (
            board_column is not serializers.empty
            and board_column is not None
            and board_column.is_final
        )
        if moving_to_final and self.instance is not None:
            already_final = bool(self.instance.board_column and self.instance.board_column.is_final)
            if not already_final:
                open_subtasks = self.instance.subtasks.filter(completed_at__isnull=True).count()
                if open_subtasks > 0:
                    raise serializers.ValidationError(
                        {"board_column": (
                            f"No se puede completar la tarea: tiene {open_subtasks} subtarea(s) "
                            "sin terminar. Completa o reasigna las subtareas primero."
                        )}
                    )

        return attrs


class TaskAssignmentSerializer(serializers.ModelSerializer):
    assigned_to_email = serializers.CharField(source="assigned_to.email", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)

    class Meta:
        model = TaskAssignment
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


class TaskAIReviewResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAIReviewResult
        fields = "__all__"
        # `user` is set from the authenticated caller in the view, never from the client.
        read_only_fields = ("id_review_result", "user", "created_at")


class GithubRepoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GithubRepo
        fields = "__all__"


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("El nickname no puede estar vacío.")
        if UserAccount.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("Este nickname ya está en uso.")
        return username


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    # Optional: the refresh token normally arrives via the HttpOnly cookie; the body is only
    # used as a fallback for legacy clients / migration.
    refresh_token = serializers.CharField(write_only=True, required=False, allow_blank=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)


class GithubOauthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()


class GithubCreateRepoSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    project_id = serializers.IntegerField(required=True, min_value=1, help_text="ID del proyecto al que se vinculará el repositorio.")
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


def _validate_hackathon_rubric(value):
    """Normalize a rubric to {category: non-negative int} over the 6 known categories.

    Accepts a dict of known category keys -> non-negative ints; rejects unknown keys and
    negative/non-integer weights; fills missing categories from the default rubric.
    """
    if value is None:
        return dict(DEFAULT_HACKATHON_RUBRIC)
    if not isinstance(value, dict):
        raise serializers.ValidationError("El rubric debe ser un objeto {categoria: peso}.")

    unknown = set(value.keys()) - set(HACKATHON_CATEGORIES)
    if unknown:
        raise serializers.ValidationError(
            f"Categorías desconocidas en el rubric: {', '.join(sorted(unknown))}. "
            f"Válidas: {', '.join(HACKATHON_CATEGORIES)}."
        )

    normalized = dict(DEFAULT_HACKATHON_RUBRIC)
    for category, weight in value.items():
        # Reject bools (a subclass of int) and non-integers; weights must be >= 0.
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise serializers.ValidationError(
                {category: "El peso debe ser un entero no negativo."}
            )
        if weight < 0:
            raise serializers.ValidationError(
                {category: "El peso no puede ser negativo."}
            )
        normalized[category] = weight
    return normalized


class HackathonSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    rubric = serializers.JSONField(required=False)

    class Meta:
        model = Hackathon
        fields = ["id_hackathon", "name", "created_by", "rubric", "status", "created_at"]
        read_only_fields = ["id_hackathon", "created_by", "status", "created_at"]

    def validate_rubric(self, value):
        return _validate_hackathon_rubric(value)

    def create(self, validated_data):
        # Always persist a full, normalized rubric (defaults applied) even when omitted.
        if "rubric" not in validated_data:
            validated_data["rubric"] = dict(DEFAULT_HACKATHON_RUBRIC)
        return super().create(validated_data)


class HackathonSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HackathonSubmission
        fields = [
            "id_submission",
            "hackathon",
            "team_name",
            "repo_url",
            "ref",
            "status",
            "score",
            "score_breakdown",
            "findings",
            "summary",
            "error",
            "created_at",
            "analyzed_at",
        ]
        # Only team_name/repo_url/ref are client-writable on create; everything else (including
        # the parent hackathon, which the view sets) is populated server-side / by the auditor.
        read_only_fields = [
            "id_submission",
            "hackathon",
            "status",
            "score",
            "score_breakdown",
            "findings",
            "summary",
            "error",
            "created_at",
            "analyzed_at",
        ]

    def validate_repo_url(self, value):
        url = (value or "").strip()
        # Must be a public GitHub repo URL: https://github.com/<owner>/<repo>
        if not re.match(r"^https://github\.com/[^/\s]+/[^/\s]+/?$", url):
            raise serializers.ValidationError(
                "repo_url debe ser una URL https://github.com/owner/repo válida."
            )
        return url


class TaskPushMatchSerializer(serializers.ModelSerializer):
    push_ref = serializers.CharField(source="push.ref", read_only=True)
    push_pusher = serializers.CharField(source="push.pusher", read_only=True, allow_null=True)
    push_received_at = serializers.DateTimeField(source="push.received_at", read_only=True)
    push_repo = serializers.CharField(source="push.repo_full_name", read_only=True)
    push_commits = serializers.JSONField(source="push.commits", read_only=True)
    push_diff_text = serializers.CharField(source="push.diff_text", read_only=True, allow_null=True)

    class Meta:
        model = TaskPushMatch
        fields = [
            "id_match",
            "coverage",
            "reason",
            "code_snippet",
            "created_at",
            "push_ref",
            "push_pusher",
            "push_received_at",
            "push_repo",
            "push_commits",
            "push_diff_text",
        ]
