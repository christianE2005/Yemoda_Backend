from django.db import models
from django.conf import settings
import hashlib
import base64
from cryptography.fernet import Fernet


class SystemRole(models.Model):
    ADMIN = "Admin"
    USER = "User"
    STAKEHOLDER = "Stakeholder"
    PROJECT_MANAGER = "Project Manager"

    ROLE_CHOICES = [
        (ADMIN, "Admin"),
        (USER, "User"),
        (STAKEHOLDER, "Stakeholder"),
        (PROJECT_MANAGER, "Project Manager"),
    ]

    id_system_role = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True, choices=ROLE_CHOICES)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "system_role"

    def __str__(self):
        return self.name


class UserAccount(models.Model):
    id_user = models.BigAutoField(primary_key=True)
    email = models.EmailField(max_length=150, unique=True)
    username = models.CharField(max_length=100)
    password_hash = models.CharField(max_length=255)
    system_role = models.ForeignKey(
        SystemRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_system_role",
        related_name="users",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_account"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_admin(self):
        return self.system_role is not None and self.system_role.name == SystemRole.ADMIN


class Project(models.Model):
    PLANNING = "Planeación"
    IN_PROGRESS = "En Progreso"
    IN_REVIEW = "Revisión"
    FINISHED = "Finalizado"
    RETIRED = "Retirado"
    CANCELLED = "Cancelado"

    STATUS_CHOICES = [
        (PLANNING, "Planeación"),
        (IN_PROGRESS, "En Progreso"),
        (IN_REVIEW, "Revisión"),
        (FINISHED, "Finalizado"),
        (RETIRED, "Retirado"),
        (CANCELLED, "Cancelado"),
    ]

    id_project = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=IN_PROGRESS)
    # Roadmap configuration
    ROADMAP_TYPE_SPRINTS = "sprints"
    ROADMAP_TYPE_CICD = "ci_cd"
    ROADMAP_TYPE_CHOICES = [
        (ROADMAP_TYPE_SPRINTS, "Sprints"),
        (ROADMAP_TYPE_CICD, "CI/CD"),
    ]
    roadmap_type = models.CharField(max_length=20, choices=ROADMAP_TYPE_CHOICES, default=ROADMAP_TYPE_SPRINTS)
    sprint_length_days = models.IntegerField(null=True, blank=True, help_text="Tamaño del sprint en días cuando roadmap_type= sprints")
    sprint_count = models.IntegerField(null=True, blank=True, help_text="Número total de sprints (opcional). Si no se especifica, se calcula usando sprint_length_days y las fechas")
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="projects_created",
    )
    github_repo_full_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    class Meta:
        db_table = "project"


class ProjectRepo(models.Model):
    id_project_repo = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="repos",
    )
    repo_full_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_repo"
        unique_together = [("project", "repo_full_name")]


class Role(models.Model):
    id_role = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "role"


class ProjectMember(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="project_memberships",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="members",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_role",
        related_name="project_members",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_member"
        unique_together = ("user", "project")


class Board(models.Model):
    id_board = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="boards",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "board"


class TaskStatus(models.Model):
    id_status = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "task_status"


class TaskPriority(models.Model):
    id_priority = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    level = models.IntegerField()

    class Meta:
        db_table = "task_priority"


class Task(models.Model):
    id_task = models.BigAutoField(primary_key=True)
    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        db_column="id_board",
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    status = models.ForeignKey(
        TaskStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_status",
        related_name="tasks",
    )
    priority = models.ForeignKey(
        TaskPriority,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_priority",
        related_name="tasks",
    )
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="tasks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    sprint = models.ForeignKey(
        "Sprint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_sprint",
        related_name="tasks",
    )
    scrum_number = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "task"


class Sprint(models.Model):
    id_sprint = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="sprints",
    )
    number = models.IntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sprint"
        unique_together = ("project", "number")
        ordering = ["project_id", "number"]

    def __str__(self):
        return f"{self.project.name} - Sprint {self.number}"


class TaskAssignment(models.Model):
    id_assignment = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="assignments",
    )
    assigned_to = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="task_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_assignment"
        unique_together = ("task", "assigned_to")


class TaskComment(models.Model):
    id_comment = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="comments",
    )
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_user",
        related_name="task_comments",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_comment"


class ActivityLog(models.Model):
    id_activity = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_user",
        related_name="activities",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_project",
        related_name="activity_logs",
    )
    entity_type = models.CharField(max_length=50, null=True, blank=True)
    entity_id = models.IntegerField(null=True, blank=True)
    action = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_log"


class GithubConnection(models.Model):
    id_connection = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="github_connection",
    )
    github_user_id = models.BigIntegerField(unique=True)
    github_login = models.CharField(max_length=150)
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_connection"


class GithubAppInstallation(models.Model):
    id_installation = models.BigAutoField(primary_key=True)
    installation_id = models.BigIntegerField(unique=True)
    account_login = models.CharField(max_length=150)
    account_type = models.CharField(max_length=50, null=True, blank=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_user",
        related_name="github_app_installations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_app_installation"


class ExternalConnection(models.Model):
    PROVIDER_AZURE = "azure_devops"
    PROVIDER_JIRA = "jira"
    PROVIDER_GITHUB_ISSUES = "github_issues"

    PROVIDER_CHOICES = [
        (PROVIDER_AZURE, "Azure DevOps"),
        (PROVIDER_JIRA, "Jira"),
        (PROVIDER_GITHUB_ISSUES, "GitHub Issues"),
    ]

    id_connection = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="id_project",
        related_name="external_connections",
    )
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default=PROVIDER_AZURE)
    name = models.CharField(max_length=150)
    organization = models.CharField(max_length=255, null=True, blank=True)
    instance_url = models.CharField(max_length=500, null=True, blank=True)
    encrypted_token = models.TextField(null=True, blank=True)
    encrypted_refresh_token = models.TextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="external_connections_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "external_connection"

    @staticmethod
    def _fernet_key() -> bytes:
        # Derive a 32-byte key from Django SECRET_KEY using SHA256 and encode for Fernet
        secret = (settings.SECRET_KEY or "").encode("utf-8")
        key = hashlib.sha256(secret).digest()
        return base64.urlsafe_b64encode(key)

    def set_token(self, token: str) -> None:
        if not token:
            self.encrypted_token = None
            return
        f = Fernet(self._fernet_key())
        self.encrypted_token = f.encrypt(token.encode()).decode()

    def get_token(self) -> str | None:
        if not self.encrypted_token:
            return None
        f = Fernet(self._fernet_key())
        try:
            return f.decrypt(self.encrypted_token.encode()).decode()
        except Exception:
            return None

    def set_refresh_token(self, refresh_token: str) -> None:
        if not refresh_token:
            self.encrypted_refresh_token = None
            return
        f = Fernet(self._fernet_key())
        self.encrypted_refresh_token = f.encrypt(refresh_token.encode()).decode()

    def get_refresh_token(self) -> str | None:
        if not self.encrypted_refresh_token:
            return None
        f = Fernet(self._fernet_key())
        try:
            return f.decrypt(self.encrypted_refresh_token.encode()).decode()
        except Exception:
            return None


class GithubPushEvent(models.Model):
    id_push = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="id_project",
        related_name="push_events",
    )
    repo_full_name = models.CharField(max_length=255)
    ref = models.CharField(max_length=255)
    pusher = models.CharField(max_length=150, null=True, blank=True)
    commits = models.JSONField(default=list)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "github_push_event"
        ordering = ["-received_at"]


class TaskWarning(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    id_warning = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="warnings",
    )
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_in_push = models.ForeignKey(
        GithubPushEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_push_created",
        related_name="created_warnings",
    )
    resolved_in_push = models.ForeignKey(
        GithubPushEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_push_resolved",
        related_name="resolved_warnings",
    )

    class Meta:
        db_table = "task_warning"
        ordering = ["-created_at"]


class TaskPushMatch(models.Model):
    COVERAGE_FULL = "full"
    COVERAGE_PARTIAL = "partial"
    COVERAGE_CHOICES = [
        (COVERAGE_FULL, "Full"),
        (COVERAGE_PARTIAL, "Partial"),
    ]

    id_match = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="push_matches",
    )
    push = models.ForeignKey(
        GithubPushEvent,
        on_delete=models.CASCADE,
        db_column="id_push",
        related_name="task_matches",
    )
    coverage = models.CharField(max_length=10, choices=COVERAGE_CHOICES, default=COVERAGE_PARTIAL)
    reason = models.TextField(null=True, blank=True)
    code_snippet = models.TextField(null=True, blank=True)
    # ML metadata
    similarity = models.FloatField(null=True, blank=True)
    model_name = models.CharField(max_length=200, null=True, blank=True)

    FEEDBACK_UNKNOWN = "unknown"
    FEEDBACK_CORRECT = "correct"
    FEEDBACK_INCORRECT = "incorrect"
    FEEDBACK_CHOICES = [
        (FEEDBACK_UNKNOWN, "Unknown"),
        (FEEDBACK_CORRECT, "Correct"),
        (FEEDBACK_INCORRECT, "Incorrect"),
    ]
    feedback = models.CharField(max_length=20, choices=FEEDBACK_CHOICES, default=FEEDBACK_UNKNOWN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_push_match"
        ordering = ["-created_at"]
        unique_together = ("task", "push")


class GithubRepo(models.Model):
    id_repo = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="github_repos",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_project",
        related_name="github_repos",
    )
    github_repo_id = models.BigIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    owner = models.CharField(max_length=150)
    private = models.BooleanField(default=True)
    html_url = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "github_repo"
        ordering = ["-created_at"]
