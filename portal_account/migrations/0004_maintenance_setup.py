# Sets up the Maintenance section and the scheduled cleanup it watches:
#   * the ``view_maintenance`` permission and the "Infra maintainers" group
#     that grants it;
#   * the django-celery-beat periodic task that deletes unverified accounts.
# Names are copied literally rather than imported from portal_account: a data
# migration is a historical record and must stay replayable on a fresh
# database. See docs/architecture/signup-abuse-protection.md.

from django.db import migrations

MAINTAINERS_GROUP = "Infra maintainers"
PERMISSION_CODENAME = "view_maintenance"
PERMISSION_NAME = "Can view the maintenance section"

TASK_NAME = "Delete unverified accounts"
TASK_PATH = "portal_account.tasks.delete_unverified_accounts_task"


def create_maintainers_group(apps, schema_editor):
    """Create the group and attach the permission.

    Permission rows are normally created by the post_migrate signal, which
    runs after every migration, so on a fresh database the row does not exist
    yet; create it here rather than look it up.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="portal_account", model="portalprofile"
    )
    permission, _ = Permission.objects.get_or_create(
        codename=PERMISSION_CODENAME,
        content_type=content_type,
        defaults={"name": PERMISSION_NAME},
    )
    group, _ = Group.objects.get_or_create(name=MAINTAINERS_GROUP)
    group.permissions.add(permission)


def delete_maintainers_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=MAINTAINERS_GROUP).delete()


def seed_periodic_tasks(apps, schema_editor):
    """Schedule the deletion job daily at 03:00 UTC.

    The schedule is data (editable under "Periodic tasks" in the Django
    admin); this only gives a fresh database the same default.
    """
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    daily_at_three, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "crontab": daily_at_three,
            "description": (
                "Delete accounts that never verified their email address "
                "within UNVERIFIED_ACCOUNT_RETENTION_DAYS."
            ),
        },
    )


def unseed_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("portal_account", "0003_portalprofile_tos_agreement"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="portalprofile",
            options={
                "permissions": [
                    ("view_maintenance", "Can view the maintenance section")
                ]
            },
        ),
        migrations.RunPython(create_maintainers_group, delete_maintainers_group),
        migrations.RunPython(seed_periodic_tasks, unseed_periodic_tasks),
    ]
