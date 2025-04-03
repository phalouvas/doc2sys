import frappe
from frappe import _

def get_context(context):
    if frappe.session.user == 'Guest':
        frappe.local.flags.redirect_location = '/login'
        raise frappe.Redirect
    
    # Check if user has Customer role
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Customer"}):
        frappe.throw(_("You need Customer role to access this page"))
    
    context.no_cache = 1
    context.show_sidebar = True
    
    # Get user's current keys if they exist
    user = frappe.get_doc("User", frappe.session.user)
    context.api_key = user.api_key
    
    # Don't expose the API secret in the context
    # It will only be shown once after generation
    context.has_api_secret = bool(user.get_password("api_secret"))
    
    return context