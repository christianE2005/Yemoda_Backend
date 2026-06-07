from django.db import models


class UserAccount(models.Model):
    PLAN_MONTHLY = "monthly"
    PLAN_ANNUAL = "annual"
    PLAN_CHOICES = [
        (PLAN_MONTHLY, "Monthly"),
        (PLAN_ANNUAL, "Annual"),
    ]

    id_user = models.BigAutoField(primary_key=True)
    email = models.EmailField(max_length=150, unique=True)
    username = models.CharField(max_length=100)
    password_hash = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    subscription_plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        null=True,
        blank=True,
        help_text="Active subscription tier: 'monthly' or 'annual'. Null means free tier.",
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Stripe subscription ID (sub_xxx). Required to cancel/modify subscription.",
    )
    stripe_customer_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Stripe customer ID (cus_xxx).",
    )
    is_email_verified = models.BooleanField(default=False)
    # Bumped on password change / logout to invalidate all previously-issued JWTs.
    token_version = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_account"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True



class Project(models.Model):
    PLANNING = "Planning"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "Review"
    FINISHED = "Finished"
    RETIRED = "Retired"
    CANCELLED = "Cancelled"

    STATUS_CHOICES = [
        (PLANNING,    "Planning"),
        (IN_PROGRESS, "In Progress"),
        (IN_REVIEW,   "Review"),
        (FINISHED,    "Finished"),
        (RETIRED,     "Retired"),
        (CANCELLED,   "Cancelled"),
    ]

    id_project = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=PLANNING)
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="projects_created",
    )
    github_repo_full_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    review_branches = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Comma-separated branch names to trigger AI review (e.g. main,develop). Leave empty to analyze all branches.",
    )

    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_CHOICES = [(PLAN_FREE, "Free"), (PLAN_PRO, "Pro")]
    # Billing plan that drives AI quotas. Free = flat cap; Pro = per-seat allowance.
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=PLAN_FREE)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)

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
        db_table = "project_role"


class ProjectRole(models.Model):
    """Per-project, creator-managed role with granular permissions.

    Each project owns its own set of roles (seeded with defaults on creation) that the
    project creator can edit. Permissions are individual booleans; `max_move_column`
    optionally caps how far a role can move a task on the board (null = no limit).
    """

    id_project_role = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="project_roles",
    )
    name = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)
    # Full-access role (the creator's default). Cannot be deleted; all perms implicitly on.
    is_admin_role = models.BooleanField(default=False)
    # Seeded default role (editable). Kept to identify the out-of-the-box set.
    is_system = models.BooleanField(default=False)

    # ── Granular permissions ────────────────────────────────────────────────
    can_create_tasks = models.BooleanField(default=False)
    can_edit_tasks = models.BooleanField(default=False)
    can_delete_tasks = models.BooleanField(default=False)
    can_move_tasks = models.BooleanField(default=False)
    can_manage_sprints = models.BooleanField(default=False)
    can_manage_board = models.BooleanField(default=False)
    can_manage_milestones = models.BooleanField(default=False)
    can_manage_tags = models.BooleanField(default=False)
    can_comment = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    can_manage_project = models.BooleanField(default=False)
    can_trigger_ai = models.BooleanField(default=False)

    # Cap on how far a task can be moved: a task may only be moved into columns whose
    # `order` <= this column's `order`. Null = no limit (can move anywhere).
    max_move_column = models.ForeignKey(
        "BoardColumn",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_max_move_column",
        related_name="role_move_caps",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_custom_role"
        unique_together = ("project", "name")

    # Permission attribute names exposed as checkboxes / enforced in the API.
    PERMISSION_FIELDS = (
        "can_create_tasks",
        "can_edit_tasks",
        "can_delete_tasks",
        "can_move_tasks",
        "can_manage_sprints",
        "can_manage_board",
        "can_manage_milestones",
        "can_manage_tags",
        "can_comment",
        "can_manage_members",
        "can_manage_project",
        "can_trigger_ai",
    )


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
    # Per-project custom role that actually drives authorization. The legacy `role` FK
    # (global) is kept for backward compatibility but no longer used for enforcement.
    project_role = models.ForeignKey(
        ProjectRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_project_role",
        related_name="members",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_member"
        unique_together = ("user", "project")


class Board(models.Model):
    CODING_STYLE_CHOICES = [
        ("standard", "Standard"),
        ("clean_code", "Clean Code / SOLID"),
        ("tdd", "Test-Driven Development"),
        ("security", "Security-First"),
        ("performance", "Performance & Optimization"),
    ]

    REVIEW_FOCUS_CHOICES = [
        ("strict", "Strict — Story & acceptance criteria only"),
        ("general", "General — Story + code quality suggestions"),
    ]

    TECH_STACK_CHOICES = [
        ("mixed", "Mixed / Full-Stack"),
        ("python", "Python"),
        ("nodejs", "Node.js / JavaScript"),
        ("typescript", "TypeScript / Node.js"),
        ("java", "Java / Spring"),
        ("go", "Go"),
        ("dotnet", "C# / .NET"),
        ("react", "React"),
        ("nextjs", "Next.js"),
        ("angular", "Angular"),
        ("vue", "Vue.js"),
        ("vite", "Vite / Vanilla JS"),
    ]

    NAMING_CONVENTION_CHOICES = [
        ("default", "Language defaults"),
        ("camel_case", "camelCase"),
        ("pascal_case", "PascalCase"),
        ("snake_case", "snake_case"),
        ("kebab_case", "kebab-case"),
        ("mixed", "Mixed (snake_case + camelCase + PascalCase)"),
    ]

    RESPONSE_LANGUAGE_CHOICES = [
        ("es", "Español"),
        ("en", "English"),
    ]

    id_board = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column="id_project",
        related_name="boards",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    coding_style = models.CharField(
        max_length=20,
        choices=CODING_STYLE_CHOICES,
        default="standard",
    )
    review_focus = models.CharField(
        max_length=10,
        choices=REVIEW_FOCUS_CHOICES,
        default="general",
    )
    tech_stack = models.CharField(
        max_length=20,
        choices=TECH_STACK_CHOICES,
        default="mixed",
    )
    naming_convention = models.CharField(
        max_length=20,
        choices=NAMING_CONVENTION_CHOICES,
        default="default",
    )
    response_language = models.CharField(
        max_length=5,
        choices=RESPONSE_LANGUAGE_CHOICES,
        default="es",
    )
    custom_instructions = models.TextField(null=True, blank=True)
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
    is_review = models.BooleanField(default=False)

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
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="id_parent_task",
        related_name="subtasks",
        help_text=(
            "Parent task. A task with a parent is a subtask. Supports arbitrary depth "
            "(epic -> story -> subtask). Deleting a parent cascades to its subtasks."
        ),
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
    scrum_number = models.PositiveIntegerField(null=True, blank=True)
    story_points = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "task"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "scrum_number"],
                condition=models.Q(scrum_number__isnull=False),
                name="unique_task_scrum_number_per_project",
            )
        ]

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
    diff_text = models.TextField(null=True, blank=True)
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

    SEVERITY_CRITICAL = "critical"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_INFO, "Info"),
    ]

    id_warning = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="warnings",
    )
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
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


class TaskAIReviewResult(models.Model):
    PROVIDER_COPILOT = "copilot"
    PROVIDER_YEMODA = "yemoda"
    PROVIDER_CHOICES = [
        (PROVIDER_COPILOT, "Copilot"),
        (PROVIDER_YEMODA, "Yemoda"),
    ]

    id_review_result = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        db_column="id_task",
        related_name="ai_review_results",
    )
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_user",
        related_name="ai_review_results",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    model_name = models.CharField(max_length=100, null=True, blank=True)
    result_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_ai_review_result"
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


class ProjectAiUsage(models.Model):
    """Per-project, per-month counter of AI calls by category, for quota enforcement."""
    id_usage = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, db_column="id_project", related_name="ai_usage")
    period = models.CharField(max_length=7)  # "YYYY-MM"
    reviews_used = models.IntegerField(default=0)
    chat_used = models.IntegerField(default=0)
    aifix_used = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project_ai_usage"
        unique_together = ("project", "period")


class PendingAiReview(models.Model):
    """A push review deferred because the project's monthly review quota was exhausted (retried later)."""
    id_pending = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, db_column="id_project", related_name="pending_ai_reviews")
    push = models.ForeignKey(GithubPushEvent, on_delete=models.CASCADE, db_column="id_push", related_name="pending_reviews")
    trigger = models.CharField(max_length=20, default="push")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pending_ai_review"
        ordering = ["created_at"]


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


class StripePayment(models.Model):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    id_payment = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="stripe_payments",
    )
    checkout_session_id = models.CharField(max_length=255, unique=True)
    plan = models.CharField(max_length=20, null=True, blank=True, help_text="'monthly' or 'annual'")
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    amount_total = models.IntegerField(null=True, blank=True, help_text="Amount in cents")
    currency = models.CharField(max_length=10, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stripe_payment"
        ordering = ["-created_at"]


class Hackathon(models.Model):
    """A hackathon a judge (owner) runs: holds the scoring rubric and groups submissions."""
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    MODE_NORMAL = "normal"
    MODE_BATCH = "batch"
    PROCESSING_MODE_CHOICES = [
        (MODE_NORMAL, "Normal"),
        (MODE_BATCH, "Batch"),
    ]

    id_hackathon = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="id_user",
        related_name="hackathons_created",
    )
    # category -> integer weight chosen by the judge (weight 0 means "ignore in the overall").
    rubric = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    # 'normal' scores each submission live; 'batch' uses Anthropic Message Batches (cheaper, async).
    processing_mode = models.CharField(
        max_length=10,
        choices=PROCESSING_MODE_CHOICES,
        default=MODE_NORMAL,
    )
    # Number of teams the judge expects, used only for the price quote.
    expected_teams = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hackathon"
        ordering = ["-created_at"]


class HackathonSubmission(models.Model):
    """A team's repo submission to a hackathon; scored asynchronously by the FastAPI auditor."""
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    # Batch mode: submitted to an Anthropic Message Batch, awaiting its result.
    STATUS_BATCH_PENDING = "batch_pending"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
        (STATUS_BATCH_PENDING, "Batch pending"),
    ]

    id_submission = models.BigAutoField(primary_key=True)
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        db_column="id_hackathon",
        related_name="submissions",
    )
    team_name = models.CharField(max_length=150)
    repo_url = models.CharField(max_length=500)
    ref = models.CharField(max_length=255, default="main")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # 0..100 weighted overall, computed by the auditor.
    score = models.IntegerField(null=True, blank=True)
    # {category: {score: 0..100, weight: int}}
    score_breakdown = models.JSONField(null=True, blank=True)
    # [{category, severity, title, file, description}]
    findings = models.JSONField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    # Anthropic Message Batch id this submission was sent in (batch mode only).
    batch_id = models.CharField(max_length=255, null=True, blank=True)
    # Batch bookkeeping: {n_chunks:int, chunks:[{idx,char_len}], rubric:{cat:int}}.
    batch_meta = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hackathon_submission"
        ordering = ["-created_at"]


class EmailVerificationToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        db_column="id_user",
        related_name="verification_tokens",
    )
    token = models.CharField(max_length=100, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_verification_token"
