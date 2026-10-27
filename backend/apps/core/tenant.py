# apps/core/tenant.py
"""
Request-scoped tenant storage.

Stores the current organization on a thread-local so deep service functions
can access it without threading `request` through every signature.

Usage from a view:
    from apps.core.tenant import set_current_organization, clear_current_organization
    set_current_organization(org)
    try:
        ...
    finally:
        clear_current_organization()
"""
import threading

_local = threading.local()


def set_current_organization(org):
    _local.organization = org


def get_current_organization():
    return getattr(_local, 'organization', None)


def clear_current_organization():
    if hasattr(_local, 'organization'):
        del _local.organization