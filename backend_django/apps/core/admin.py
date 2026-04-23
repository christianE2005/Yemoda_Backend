from django.contrib import admin

from .models import (
    ActivityLog,
    Board,
    GithubAppInstallation,
    GithubConnection,
    GithubPushEvent,
    GithubRepo,
    Project,
    ProjectMember,
    ProjectRepo,
    Role,
    SystemRole,
    Task,
    TaskAssignment,
    TaskComment,
    TaskPriority,
    TaskPushMatch,
    TaskStatus,
    TaskWarning,
    UserAccount,
)

admin.site.register(UserAccount)
admin.site.register(SystemRole)
admin.site.register(Project)
admin.site.register(ProjectRepo)
admin.site.register(Role)
admin.site.register(ProjectMember)
admin.site.register(Board)
admin.site.register(TaskStatus)
admin.site.register(TaskPriority)
admin.site.register(Task)
admin.site.register(TaskAssignment)
admin.site.register(TaskComment)
admin.site.register(TaskWarning)
admin.site.register(TaskPushMatch)
admin.site.register(ActivityLog)
admin.site.register(GithubConnection)
admin.site.register(GithubAppInstallation)
admin.site.register(GithubPushEvent)
admin.site.register(GithubRepo)
