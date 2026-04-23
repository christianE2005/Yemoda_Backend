from django.db import migrations


class Migration(migrations.Migration):
    """
    Merge the two parallel branches that both depend on 0020_project_repo:
      - 0021_activitylog_project  (adds activity_log.id_project column)
      - 0022_merge_0020_project_repo_0021_insert_stakeholder_role
    """

    dependencies = [
        ("core", "0021_activitylog_project"),
        ("core", "0022_merge_0020_project_repo_0021_insert_stakeholder_role"),
    ]

    operations = []
