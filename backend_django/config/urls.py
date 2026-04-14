from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.core.views import (
    ActivityLogViewSet,
    BoardViewSet,
    GithubAppInstallStartView,
    GithubAppLinkInstallationView,
    GithubAppOauthCallbackView,
    GithubAppOauthStartView,
    GithubConnectionStatusView,
    GithubCreateRepoView,
    GithubPushWebhookView,
    LoginView,
    ProjectMemberViewSet,
    ProjectViewSet,
    RefreshView,
    RegisterView,
    RoleViewSet,
    TaskCommentViewSet,
    TaskPriorityViewSet,
    TaskStatusViewSet,
    TaskViewSet,
    UserAccountViewSet,
)

router = DefaultRouter()
router.register(r"user-accounts", UserAccountViewSet)
router.register(r"projects", ProjectViewSet)
router.register(r"roles", RoleViewSet)
router.register(r"project-members", ProjectMemberViewSet)
router.register(r"boards", BoardViewSet)
router.register(r"task-statuses", TaskStatusViewSet)
router.register(r"task-priorities", TaskPriorityViewSet)
router.register(r"tasks", TaskViewSet)
router.register(r"task-comments", TaskCommentViewSet)
router.register(r"activity-logs", ActivityLogViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("api/github/app/install/start/", GithubAppInstallStartView.as_view(), name="github-app-install-start"),
    path("api/github/app/oauth/start/", GithubAppOauthStartView.as_view(), name="github-app-oauth-start"),
    path("api/github/app/oauth/callback/", GithubAppOauthCallbackView.as_view(), name="github-app-oauth-callback"),
    path("api/github/app/install/link/", GithubAppLinkInstallationView.as_view(), name="github-app-install-link"),
    path("api/github/repos/", GithubCreateRepoView.as_view(), name="github-create-repo"),
    path("api/github/connection/status/", GithubConnectionStatusView.as_view(), name="github-connection-status"),
    path("api/github/webhook/push/", GithubPushWebhookView.as_view(), name="github-push-webhook"),
    path("api/", include(router.urls)),
]
