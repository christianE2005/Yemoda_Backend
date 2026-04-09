from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.core.views import (
    ActivityLogViewSet,
    BoardViewSet,
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
    path("api/", include(router.urls)),
]
