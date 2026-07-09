from .models import CustomPermission, RoleCustomPermission, UserCustomPermission


def user_has_custom_permission(user, permission_code):
    if not permission_code:
        return True

    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    permission = CustomPermission.objects.filter(code=permission_code, is_active=True).first()
    if not permission:
        return False

    # User-level explicit deny overrides any grant.
    user_assignments = UserCustomPermission.objects.filter(user=user, permission=permission)
    if user_assignments.filter(is_granted=False).exists():
        return False
    if user_assignments.filter(is_granted=True).exists():
        return True

    account_profile = getattr(user, "account_profile", None)
    if not account_profile:
        return False

    # Role-level explicit deny overrides role-level grant.
    role_assignments = RoleCustomPermission.objects.filter(role=account_profile.role, permission=permission)
    if role_assignments.filter(is_granted=False).exists():
        return False
    if role_assignments.filter(is_granted=True).exists():
        return True

    return False
