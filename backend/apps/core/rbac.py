from apps.core.permissions import (
    ROLE_HQ_ADMIN, ROLE_BRANCH_MANAGER, ROLE_LOAN_OFFICER, ROLE_TELLER,
)


def is_hq(user):
    return user.is_superuser or user.role == ROLE_HQ_ADMIN


def is_branch_manager(user):
    return user.is_superuser or user.role == ROLE_BRANCH_MANAGER


def is_loan_officer(user):
    return user.is_superuser or user.role == ROLE_LOAN_OFFICER


def is_teller(user):
    return user.is_superuser or user.role == ROLE_TELLER


def is_platform_admin(user):
    return (
        user.is_superuser
        or getattr(user, 'is_platform_admin', False)
    )


def can_view_all_branches(user):
    # Only HQ or platform admin can see all branches within their tenant
    return is_hq(user) or is_platform_admin(user)


def get_user_branch_id(user):
    return getattr(user, 'branch_id', None)


def get_user_org_id(user):
    return getattr(user, 'organization_id', None)


def scope_queryset_by_org(queryset, user, org_field='organization'):
    """
    Scope a queryset to the user's organization.

    - Anonymous → empty
    - Platform admin → no filter (see everything)
    - Tenant user → filter by organization
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return queryset.none()

    if is_platform_admin(user) and not get_user_org_id(user):
        return queryset

    org_id = get_user_org_id(user)
    if org_id is None:
        return queryset.none()

    return queryset.filter(**{f'{org_field}_id': org_id})


def scope_queryset_by_branch(queryset, user, branch_field='branch'):
    """
    Apply BOTH organization and branch scoping.

    - Anonymous → empty
    - Platform admin → no filter
    - HQ admin → filter by org only
    - Others → filter by branch (which is inside their org)
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return queryset.none()

    # Platform admin sees all
    if is_platform_admin(user) and not get_user_org_id(user):
        return queryset

    org_id = get_user_org_id(user)
    if org_id is None:
        return queryset.none()

    # Always filter by org first
    qs = queryset.filter(**{f'{branch_field}__organization_id': org_id})

    # HQ admin sees all branches in org
    if is_hq(user):
        return qs

    # Others see only their branch
    branch_id = get_user_branch_id(user)
    if branch_id is None:
        return qs.none()

    return qs.filter(**{f'{branch_field}_id': branch_id})