from rest_framework import permissions
from rest_framework.permissions import BasePermission


# ============================================================
# Role Constants
# ============================================================
ROLE_HQ_ADMIN = 'HQ_ADMIN'
ROLE_BRANCH_MANAGER = 'BRANCH_MANAGER'
ROLE_LOAN_OFFICER = 'LOAN_OFFICER'
ROLE_TELLER = 'TELLER'

ALL_ROLES = [ROLE_HQ_ADMIN, ROLE_BRANCH_MANAGER, ROLE_LOAN_OFFICER, ROLE_TELLER]


# ============================================================
# Base Permission — the "is this user allowed to do anything?"
# ============================================================
class IsAuthenticatedStaff(permissions.BasePermission):
    """
    Base: user must be authenticated and have a valid role.
    Superusers always pass.
    """
    message = "You must be an authenticated staff member."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in ALL_ROLES


# ============================================================
# Role-based permissions
# ============================================================
class IsHQAdmin(IsAuthenticatedStaff):
    message = "HQ Admin role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or request.user.role == ROLE_HQ_ADMIN


class IsBranchManager(IsAuthenticatedStaff):
    message = "Branch Manager role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or request.user.role == ROLE_BRANCH_MANAGER


class IsLoanOfficer(IsAuthenticatedStaff):
    message = "Loan Officer role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or request.user.role == ROLE_LOAN_OFFICER


class IsTeller(IsAuthenticatedStaff):
    message = "Teller role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or request.user.role == ROLE_TELLER


# ============================================================
# Combined role permissions
# ============================================================
class IsBranchStaff(IsAuthenticatedStaff):
    """
    Any tenant staff member: HQ_ADMIN, BRANCH_MANAGER, LOAN_OFFICER, or TELLER.

    HQ_ADMIN is included because HQ oversight requires read access to branch
    data. Branch isolation for HQ is handled by the viewset's get_queryset(),
    not by this permission — HQ admins see all branches, other roles see only
    their own.
    """
    message = "Staff role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True
        return request.user.role in [
            ROLE_HQ_ADMIN,
            ROLE_BRANCH_MANAGER,
            ROLE_LOAN_OFFICER,
            ROLE_TELLER,
        ]


class IsHQOrBranchManager(IsAuthenticatedStaff):
    """HQ_ADMIN or BRANCH_MANAGER."""
    message = "HQ Admin or Branch Manager role required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True
        return request.user.role in [ROLE_HQ_ADMIN, ROLE_BRANCH_MANAGER]


class IsHQOrBranchStaff(IsAuthenticatedStaff):
    """Any staff — HQ admin, branch manager, loan officer, teller."""
    message = "Staff role required."

    def has_permission(self, request, view):
        return super().has_permission(request, view)


# ============================================================
# Object-level: branch isolation
# ============================================================
class IsObjectInBranch(permissions.BasePermission):
    """
    Object-level branch isolation.

    Rules:
    - Superuser → always allowed
    - HQ_ADMIN → always allowed
    - User with no branch → denied (unless superuser/HQ)
    - Otherwise → object.branch must equal user.branch
    """
    message = "You do not have access to this branch's data."

    def has_object_permission(self, request, view, obj):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # Superuser bypass
        if user.is_superuser:
            return True

        # HQ admin sees everything
        if user.role == ROLE_HQ_ADMIN:
            return True

        # Branch-less non-HQ users cannot access any branch objects
        if user.branch_id is None:
            return False

        # Object must belong to the same branch
        obj_branch_id = getattr(obj, 'branch_id', None)
        if obj_branch_id is None:
            # Object has no branch (e.g., a User without branch, or LoanProduct)
            # Allow if it's not branch-scoped
            return True

        return obj_branch_id == user.branch_id


# ============================================================
# Object-level: ownership (for records created by the user)
# ============================================================
class IsOwnerOrHQ(permissions.BasePermission):
    """
    Allow if user owns the object, or is HQ / superuser.
    Use for fields like `created_by`, `loan_officer`, `received_by`.
    """
    message = "You do not own this record."
    owner_field = 'created_by'

    def has_object_permission(self, request, view, obj):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or user.role == ROLE_HQ_ADMIN:
            return True

        owner = getattr(obj, self.owner_field, None)
        return owner == user

class IsPlatformAdmin(permissions.BasePermission):
    message = "Platform admin access required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or getattr(user, 'is_platform_admin', False)

class IsHRPayroll(BasePermission):
    """
    Allows access only to HR Payroll Managers or HQ Admins.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.role in ['HR_PAYROLL', 'HQ_ADMIN'] or request.user.is_superuser)
        )