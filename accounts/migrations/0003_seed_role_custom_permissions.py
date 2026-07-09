from django.db import migrations


DEFAULT_CUSTOM_PERMISSIONS = [
    ("access.portal.administrator", "Access Administrator Portal", "Allow user to access administrator portal"),
    ("access.portal.teacher", "Access Teacher Portal", "Allow user to access teacher portal"),
    ("access.portal.student", "Access Student Portal", "Allow user to access student portal"),
    ("access.portal.parent", "Access Parent Portal", "Allow user to access parent portal"),
]

ROLE_PERMISSION_GRANTS = [
    ("admin", "access.portal.administrator"),
    ("teacher", "access.portal.teacher"),
    ("student", "access.portal.student"),
    ("parent", "access.portal.parent"),
]

DEFAULT_GROUPS = ["Administrator", "Teacher", "Student", "Parent"]


def forwards(apps, schema_editor):
    CustomPermission = apps.get_model("accounts", "CustomPermission")
    RoleCustomPermission = apps.get_model("accounts", "RoleCustomPermission")
    Group = apps.get_model("auth", "Group")

    permission_map = {}
    for code, name, description in DEFAULT_CUSTOM_PERMISSIONS:
        permission, _ = CustomPermission.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_active": True,
            },
        )
        permission_map[code] = permission

    for role, permission_code in ROLE_PERMISSION_GRANTS:
        permission = permission_map.get(permission_code)
        if not permission:
            continue
        RoleCustomPermission.objects.get_or_create(
            role=role,
            permission=permission,
            defaults={"is_granted": True},
        )

    for group_name in DEFAULT_GROUPS:
        Group.objects.get_or_create(name=group_name)


def backwards(apps, schema_editor):
    CustomPermission = apps.get_model("accounts", "CustomPermission")
    RoleCustomPermission = apps.get_model("accounts", "RoleCustomPermission")
    Group = apps.get_model("auth", "Group")

    RoleCustomPermission.objects.filter(permission__code__in=[code for code, _, _ in DEFAULT_CUSTOM_PERMISSIONS]).delete()
    CustomPermission.objects.filter(code__in=[code for code, _, _ in DEFAULT_CUSTOM_PERMISSIONS]).delete()
    Group.objects.filter(name__in=DEFAULT_GROUPS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_accountprofile_role_custompermission_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
