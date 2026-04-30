from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.core.views import (
    ActivityLogViewSet,
    BoardColumnViewSet,
    BoardViewSet,
    GithubAppDebugView,
    GithubAppInstallStartView,
    GithubAppLinkInstallationView,
    GithubAppOauthCallbackView,
    GithubAppOauthStartView,
    GithubCommitDiffView,
    GithubConnectionStatusView,
    GithubCreateRepoView,
    GithubPushListView,
    GithubPushWebhookView,
    GithubRepoContentsView,
    HealthCheckView,
    LoginView,
    MilestoneViewSet,
    ProjectMembersView,
    ProjectMemberViewSet,
    ProjectRepoDetailView,
    ProjectRepoView,
    ProjectViewSet,
    RefreshView,
    RoleViewSet,
    SprintViewSet,
    SystemRoleViewSet,
    TagViewSet,
    TaskAssignmentViewSet,
    TaskCommentViewSet,
    TaskHistoryView,
    TaskPriorityViewSet,
    TaskStatusViewSet,
    TaskViewSet,
    TaskWarningDetailView,
    TaskWarningListView,
    UserAccountViewSet,
)

router = DefaultRouter()
router.register(r"user-accounts", UserAccountViewSet)
router.register(r"projects", ProjectViewSet)
router.register(r"roles", RoleViewSet)
router.register(r"system-roles", SystemRoleViewSet)
router.register(r"project-members", ProjectMemberViewSet)
router.register(r"boards", BoardViewSet)
router.register(r"board-columns", BoardColumnViewSet)
router.register(r"sprints", SprintViewSet)
router.register(r"milestones", MilestoneViewSet)
router.register(r"tags", TagViewSet)
router.register(r"task-statuses", TaskStatusViewSet)
router.register(r"task-priorities", TaskPriorityViewSet)
router.register(r"tasks", TaskViewSet)
router.register(r"task-assignments", TaskAssignmentViewSet)
router.register(r"task-comments", TaskCommentViewSet)
router.register(r"activity-logs", ActivityLogViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", HealthCheckView.as_view(), name="health-root-no-slash"),
    path("health/", HealthCheckView.as_view(), name="health-root"),
    path("api/health", HealthCheckView.as_view(), name="health-api-no-slash"),
    path("api/health/", HealthCheckView.as_view(), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("api/github/app/install/start/", GithubAppInstallStartView.as_view(), name="github-app-install-start"),
    path("api/github/app/oauth/start/", GithubAppOauthStartView.as_view(), name="github-app-oauth-start"),
    path("api/github/app/oauth/callback/", GithubAppOauthCallbackView.as_view(), name="github-app-oauth-callback"),
    path("api/github/app/install/link/", GithubAppLinkInstallationView.as_view(), name="github-app-install-link"),
    path("api/github/debug/", GithubAppDebugView.as_view(), name="github-app-debug"),
    path("api/github/repos/", GithubCreateRepoView.as_view(), name="github-create-repo"),
    path("api/github/connection/status/", GithubConnectionStatusView.as_view(), name="github-connection-status"),
    path("api/github/webhook/push/", GithubPushWebhookView.as_view(), name="github-push-webhook"),
    path("api/github/pushes/", GithubPushListView.as_view(), name="github-push-list"),
    path("api/github/commits/diff/", GithubCommitDiffView.as_view(), name="github-commit-diff"),
    path("api/github/contents/", GithubRepoContentsView.as_view(), name="github-repo-contents"),
    path("api/task-warnings/", TaskWarningListView.as_view(), name="task-warning-list"),
    path("api/task-warnings/<int:warning_id>/", TaskWarningDetailView.as_view(), name="task-warning-detail"),
    path("api/tasks/<int:task_id>/history/", TaskHistoryView.as_view(), name="task-push-history"),
    path("api/projects/<int:project_id>/members/", ProjectMembersView.as_view(), name="project-members"),
    path("api/projects/<int:project_id>/repos/", ProjectRepoView.as_view(), name="project-repos"),
    path("api/projects/<int:project_id>/repos/<int:repo_id>/", ProjectRepoDetailView.as_view(), name="project-repo-detail"),
    path("api/", include(router.urls)),
]
