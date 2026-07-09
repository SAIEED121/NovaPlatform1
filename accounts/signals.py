import re

from django.contrib.auth.models import Permission
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import transaction
from django.db.models.signals import post_save
from django.db.models.signals import post_delete
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .activity import create_activity_log, get_tracked_models
from .models import AccountProfile, ActivityLog, LoginAttemptLog


ROLE_TO_GROUP = {
    AccountProfile.Role.ADMIN: "Administrator",
    AccountProfile.Role.TEACHER: "Teacher",
    AccountProfile.Role.STUDENT: "Student",
    AccountProfile.Role.PARENT: "Parent",
}

GROUP_PERMISSION_KEYS = {
    "Administrator": {
        "accounts",
        "students",
        "teachers",
        "courses",
        "subscriptions",
        "payments",
        "notifications",
    },
    "Teacher": {
        ("teachers", "view_teacher"),
        ("courses", "view_course"),
        ("courses", "change_course"),
        ("courses", "view_enrollment"),
        ("courses", "change_enrollment"),
        ("notifications", "view_notification"),
        ("notifications", "add_notification"),
        ("notifications", "change_notification"),
    },
    "Student": {
        ("students", "view_student"),
        ("courses", "view_course"),
        ("courses", "view_enrollment"),
        ("subscriptions", "view_studentsubscription"),
        ("payments", "view_payment"),
        ("notifications", "view_notification"),
    },
    "Parent": {
        ("notifications", "view_notification"),
    },
}


@receiver(post_migrate)
def ensure_default_groups_and_permissions(sender, **kwargs):
    admin_group, _ = Group.objects.get_or_create(name="Administrator")
    teacher_group, _ = Group.objects.get_or_create(name="Teacher")
    student_group, _ = Group.objects.get_or_create(name="Student")
    parent_group, _ = Group.objects.get_or_create(name="Parent")

    admin_permissions = Permission.objects.filter(
        content_type__app_label__in=GROUP_PERMISSION_KEYS["Administrator"]
    )
    admin_group.permissions.set(admin_permissions)

    for group, key in ((teacher_group, "Teacher"), (student_group, "Student"), (parent_group, "Parent")):
        permissions = []
        for app_label, codename in GROUP_PERMISSION_KEYS[key]:
            permission = Permission.objects.filter(
                content_type__app_label=app_label,
                codename=codename,
            ).first()
            if permission:
                permissions.append(permission)
        group.permissions.set(permissions)


@receiver(post_save, sender=AccountProfile)
def sync_account_group_membership(sender, instance, **kwargs):
    group_name = ROLE_TO_GROUP.get(instance.role)
    if not group_name:
        return

    user = instance.user
    role_group_names = set(ROLE_TO_GROUP.values())
    user.groups.remove(*Group.objects.filter(name__in=role_group_names))

    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)

    desired_is_staff = instance.role == AccountProfile.Role.ADMIN
    if user.is_staff != desired_is_staff:
        user.is_staff = desired_is_staff
        user.save(update_fields=["is_staff"])


@receiver(user_logged_in)
def log_login_activity(sender, request, user, **kwargs):
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    create_activity_log(
        event_type=ActivityLog.EventType.LOGIN,
        action="login",
        target_model="auth.User",
        target_id=user.pk,
        description=f"User {user.username} logged in",
        actor=user,
        ip_address=ip_address,
    )


def _extract_browser_and_os(user_agent):
    agent = (user_agent or "")[:512]
    browser = "Unknown"
    operating_system = "Unknown"

    browser_patterns = [
        (r"Edg/", "Edge"),
        (r"OPR/|Opera", "Opera"),
        (r"Chrome/", "Chrome"),
        (r"Firefox/", "Firefox"),
        (r"Safari/", "Safari"),
        (r"MSIE|Trident/", "Internet Explorer"),
    ]
    os_patterns = [
        (r"Windows NT", "Windows"),
        (r"Android", "Android"),
        (r"iPhone|iPad|iOS", "iOS"),
        (r"Mac OS X|Macintosh", "macOS"),
        (r"Linux", "Linux"),
    ]

    for pattern, name in browser_patterns:
        if re.search(pattern, agent, flags=re.IGNORECASE):
            browser = name
            break

    for pattern, name in os_patterns:
        if re.search(pattern, agent, flags=re.IGNORECASE):
            operating_system = name
            break

    return browser[:128], operating_system[:128]


@receiver(user_logged_out)
def log_forced_logout_audit(sender, request, user, **kwargs):
    if user is None:
        return
    if request is None:
        return

    path = getattr(request, "path", "") or ""
    if path.endswith("/logout/"):
        return

    user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:512]
    browser, operating_system = _extract_browser_and_os(user_agent)
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    LoginAttemptLog.objects.create(
        user=user,
        username=user.username,
        ip_address=ip_address,
        user_agent=user_agent,
        browser=browser,
        operating_system=operating_system,
        is_successful=False,
        failure_reason="forced_logout",
        role_key="logout",
    )


def _build_save_receiver(model):
    def _on_post_save(sender, instance, created, **kwargs):
        model_label = f"{sender._meta.app_label}.{sender.__name__}"
        is_payment = model_label == "payments.Payment"
        if created:
            if is_payment:
                create_activity_log(
                    event_type=ActivityLog.EventType.PAYMENT,
                    action="create",
                    target_model=model_label,
                    target_id=getattr(instance, "pk", ""),
                    description=f"Created payment {instance.pk}",
                )
            return

        create_activity_log(
            event_type=ActivityLog.EventType.PAYMENT if is_payment else ActivityLog.EventType.EDIT,
            action="edit",
            target_model=model_label,
            target_id=getattr(instance, "pk", ""),
            description=f"Edited {model_label}",
        )

    _on_post_save.__name__ = f"activity_post_save_{model._meta.app_label}_{model.__name__}"
    return _on_post_save


def _build_delete_receiver(model):
    def _on_post_delete(sender, instance, **kwargs):
        model_label = f"{sender._meta.app_label}.{sender.__name__}"
        is_payment = model_label == "payments.Payment"
        create_activity_log(
            event_type=ActivityLog.EventType.PAYMENT if is_payment else ActivityLog.EventType.DELETE,
            action="delete",
            target_model=model_label,
            target_id=getattr(instance, "pk", ""),
            description=f"Deleted {model_label}",
        )

    _on_post_delete.__name__ = f"activity_post_delete_{model._meta.app_label}_{model.__name__}"
    return _on_post_delete


def register_activity_log_receivers():
    for model in get_tracked_models():
        model_label = f"{model._meta.app_label}.{model.__name__}"
        if model_label == "accounts.ActivityLog":
            continue
        post_save.connect(
            _build_save_receiver(model),
            sender=model,
            weak=False,
            dispatch_uid=f"activity_post_save_{model_label}",
        )
        post_delete.connect(
            _build_delete_receiver(model),
            sender=model,
            weak=False,
            dispatch_uid=f"activity_post_delete_{model_label}",
        )


register_activity_log_receivers()
