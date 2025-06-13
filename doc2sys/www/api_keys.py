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
    
    # Check if API secret exists without throwing exception
    try:
        api_secret = user.get_password("api_secret")
        context.has_api_secret = bool(api_secret)
    except frappe.exceptions.AuthenticationError:
        context.has_api_secret = False
    
    return context