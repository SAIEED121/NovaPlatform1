from django.apps import apps

from novaplatform_backend.request_context import get_client_ip, get_current_user

from .models import ActivityLog


EXCLUDED_ACTIVITY_MODELS = {
    "accounts.ActivityLog",
    "auth.Permission",
    "contenttypes.ContentType",
    "sessions.Session",
}


def create_activity_log(*, event_type, action, target_model, target_id="", description="", metadata=None, actor=None, ip_address=None):
    metadata = metadata or {}
    if actor is None:
        actor = get_current_user()
        if actor is not None and (not actor.is_authenticated):
            actor = None
    if ip_address is None:
        ip_address = get_client_ip()

    ActivityLog.objects.create(
        actor=actor,
        event_type=event_type,
        action=action,
        target_model=target_model,
        target_id=str(target_id or ""),
        description=description,
        metadata=metadata,
        ip_address=ip_address,
    )


def _model_label(instance):
    return f"{instance._meta.app_label}.{instance.__class__.__name__}"


def track_model_edit(instance):
    model_label = _model_label(instance)
    if model_label in EXCLUDED_ACTIVITY_MODELS:
        return

    event_type = ActivityLog.EventType.PAYMENT if model_label == "payments.Payment" else ActivityLog.EventType.EDIT
    create_activity_log(
        event_type=event_type,
        action="edit",
        target_model=model_label,
        target_id=getattr(instance, "pk", ""),
        description=f"Edited {model_label}",
    )


def track_model_delete(instance):
    model_label = _model_label(instance)
    if model_label in EXCLUDED_ACTIVITY_MODELS:
        return

    event_type = ActivityLog.EventType.PAYMENT if model_label == "payments.Payment" else ActivityLog.EventType.DELETE
    create_activity_log(
        event_type=event_type,
        action="delete",
        target_model=model_label,
        target_id=getattr(instance, "pk", ""),
        description=f"Deleted {model_label}",
    )


def should_track_instance(instance):
    model_label = _model_label(instance)
    if model_label in EXCLUDED_ACTIVITY_MODELS:
        return False

    tracked_apps = {
        "accounts",
        "students",
        "teachers",
        "courses",
        "payments",
        "subscriptions",
        "notifications",
    }
    return instance._meta.app_label in tracked_apps


def should_track_model(model):
    model_label = f"{model._meta.app_label}.{model.__name__}"
    if model_label in EXCLUDED_ACTIVITY_MODELS:
        return False

    tracked_apps = {
        "accounts",
        "students",
        "teachers",
        "courses",
        "payments",
        "subscriptions",
        "notifications",
    }
    return model._meta.app_label in tracked_apps


def get_tracked_models():
    return [model for model in apps.get_models() if should_track_model(model)]
