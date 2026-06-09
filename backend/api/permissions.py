"""Права доступа к задачам парсинга."""
from rest_framework.permissions import BasePermission

from core.models import ParsingTask


def user_can_access_task(user, task: ParsingTask) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if task.user_id is None:
        return True
    return task.user_id == user.id


class IsTaskOwnerOrStaff(BasePermission):
    """Доступ к задаче только владельцу или staff."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return user_can_access_task(request.user, obj)
