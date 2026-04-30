from django.db import models


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
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=IN_PROGRESS)
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


class BoardColumn(models.Model):
    id_column = models.BigAutoField(primary_key=True)
    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        db_column="id_board",
        related_name="columns",
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_final = models.BooleanField(default=False)

    class Meta:
        db_table = "board_column"
        ordering = ["order"]

    def __str__(self):
        return f"{self.board.name} — {self.name}"


class Sprint(models.Model):
    PLANNED = "planned"
    ACTIVE = "active"
    CLOSED = "closed"

    STATUS_CHOICES = [
        (PLANNED, "Planned"),
        (ACTIVE, "Active"),
        (CLOSED, "Closed"),
    ]

    id_sprint = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="sprints",
    )
    name = models.CharField(max_length=150)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PLANNED)

    class Meta:
        db_table = "sprint"

    def __str__(self):
        return self.name


class Milestone(models.Model):
    id_milestone = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="milestones",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        db_table = "milestone"

    def __str__(self):
        return self.name


class Tag(models.Model):
    id_tag = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="tags",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        db_table = "tag"
        unique_together = ("project", "name")

    def __str__(self):
        return self.name


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
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="tasks",
    )
    sprint = models.ForeignKey(
        Sprint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_sprint",
        related_name="tasks",
    )
    board_column = models.ForeignKey(
        BoardColumn,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_column",
        related_name="tasks",
    )
    milestone = models.ForeignKey(
        Milestone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_milestone",
        related_name="tasks",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="tasks",
        db_table="task_tag",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
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

    class Meta:
        db_table = "task"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.board_column_id is not None:
            col = BoardColumn.objects.filter(pk=self.board_column_id).first()
            if col is not None:
                if col.is_final and not self.completed_at:
                    self.completed_at = timezone.now()
                elif not col.is_final:
                    self.completed_at = None
        else:
            self.completed_at = None
        super().save(*args, **kwargs)


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
