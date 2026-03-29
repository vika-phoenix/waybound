"""
apps/tours/permissions.py  —  Task 18
Custom DRF permission classes for tour operations.
"""
from rest_framework.permissions import BasePermission


class IsOperator(BasePermission):
    """Allow access only to users with role='operator'."""
    message = 'Only operator accounts can perform this action.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in ('operator', 'admin')
        )


class IsOperatorOwner(BasePermission):
    """Allow write access only to the operator who owns the tour."""
    message = 'You do not own this tour.'

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return hasattr(obj, 'operator') and obj.operator == request.user
