from rest_framework.permissions import BasePermission


class IsOrderOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        return bool(request.user and request.user.is_staff) or obj.user_id == request.user.id


class CanAccessPaidOrderOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return obj.user_id == request.user.id and obj.is_paid


class CanAccessGuestOrder(BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.user_id is not None or not obj.is_guest:
            return False
        return obj.guest_token_is_valid()


class CanAccessGuestPaidOrder(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not obj.is_paid:
            return False
        return CanAccessGuestOrder().has_object_permission(request, view, obj)


class IsStaffUserPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
