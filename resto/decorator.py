import frappe


def has_resto_permission(permission, user=None):
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)

    settings = frappe.get_single("Resto Settings")

    for row in settings.permissions:
        if row.role in roles and row.permission == permission:
            return True

    return False

from functools import wraps
import frappe


def check_permission(permission):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not has_resto_permission(permission):
                frappe.throw(f"You are not allowed to perform: {permission}")
            return func(*args, **kwargs)
        return wrapper
    return decorator