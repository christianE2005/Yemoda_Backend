from django.contrib import admin

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

admin.site.register(UserAccount)
admin.site.register(Project)
admin.site.register(Role)
admin.site.register(ProjectMember)
admin.site.register(Board)
admin.site.register(TaskStatus)
admin.site.register(TaskPriority)
admin.site.register(Task)
admin.site.register(TaskComment)
admin.site.register(ActivityLog)
