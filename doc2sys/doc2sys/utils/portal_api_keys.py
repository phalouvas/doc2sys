import frappe
import os
import secrets
from frappe import _
from frappe.utils import get_url, cstr

@frappe.whitelist(allow_guest=False)
def generate_api_keys_for_portal_user():
    """Generate API key and API secret for portal user with Customer role"""
    # Ensure user is a portal user with Customer role
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Customer"}):
        frappe.throw(_("Access denied: Customer role required"))
    
    # Only allow users to generate keys for themselves
    user = frappe.get_doc("User", frappe.session.user)
    
    # Generate a random api key and api secret
    api_key = frappe.generate_hash(length=15)
    api_secret = secrets.token_hex(32)
    
    # Set API key and API secret
    user.api_key = api_key
    user.api_secret = api_secret
    user.save(ignore_permissions=True)
    
    # Generate sid for the key
    key = f"{api_key}:{api_secret}"
    frappe.cache.set_value(f"api_key:{api_key}", user.name)
    
    return {
        "api_key": api_key,
        "api_secret": api_secret
    }

@frappe.whitelist(allow_guest=False)
def get_user_api_key():
    """Get the current user's API key (but not secret)"""
    # Ensure user is a portal user with Customer role
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Customer"}):
        frappe.throw(_("Access denied: Customer role required"))
    
    user = frappe.get_doc("User", frappe.session.user)
    return {"api_key": user.api_key or ""}