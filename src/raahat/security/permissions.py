"""Roles and the permissions each one carries.

Permissions are checked by the backend on every route. The frontend receives
the caller's permission list only to decide which controls to render; hiding a
control is never the enforcement.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    DISPATCHER = "dispatcher"
    RESOURCE_COORDINATOR = "resource_coordinator"
    OBSERVER = "observer"


class Permission(str, Enum):
    REPORTS_READ = "reports:read"
    REPORTS_CREATE = "reports:create"
    INCIDENTS_READ = "incidents:read"
    INCIDENTS_UPDATE = "incidents:update"
    INCIDENTS_VERIFY = "incidents:verify"
    INCIDENTS_MERGE = "incidents:merge"
    LOCATIONS_CONFIRM = "locations:confirm"
    RESOURCES_READ = "resources:read"
    RESOURCES_MANAGE = "resources:manage"
    DISPATCH_READ = "dispatch:read"
    DISPATCH_DECIDE = "dispatch:decide"
    DISPATCH_PROGRESS = "dispatch:progress"
    CALLER_PII_READ = "pii:read"
    AUDIT_READ = "audit:read"
    SYSTEM_READ = "system:read"
    SYSTEM_MANAGE = "system:manage"
    OPERATIONS_MANAGE = "operations:manage"
    USERS_MANAGE = "users:manage"


P = Permission

_READ_ONLY = frozenset(
    {
        P.REPORTS_READ,
        P.INCIDENTS_READ,
        P.RESOURCES_READ,
        P.DISPATCH_READ,
        P.SYSTEM_READ,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    # Takes reports, reviews and verifies incidents, confirms locations,
    # resolves duplicates. Sees recommendations but does not commit resources.
    Role.OPERATOR: _READ_ONLY
    | {
        P.REPORTS_CREATE,
        P.INCIDENTS_UPDATE,
        P.INCIDENTS_VERIFY,
        P.INCIDENTS_MERGE,
        P.LOCATIONS_CONFIRM,
        P.CALLER_PII_READ,
        P.AUDIT_READ,
    },
    # Commits resources to incidents and tracks the response.
    Role.DISPATCHER: _READ_ONLY
    | {
        P.REPORTS_CREATE,
        P.INCIDENTS_UPDATE,
        P.INCIDENTS_VERIFY,
        P.LOCATIONS_CONFIRM,
        P.DISPATCH_DECIDE,
        P.DISPATCH_PROGRESS,
        P.CALLER_PII_READ,
        P.AUDIT_READ,
    },
    # Maintains the resource register and reports field progress. No caller data.
    Role.RESOURCE_COORDINATOR: _READ_ONLY
    | {
        P.RESOURCES_MANAGE,
        P.DISPATCH_PROGRESS,
    },
    Role.OBSERVER: _READ_ONLY,
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def role_has(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
