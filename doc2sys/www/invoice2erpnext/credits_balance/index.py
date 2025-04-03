import frappe
from frappe import _ 
from frappe.utils import fmt_money

def get_context(context):
    # Get the system default currency
    currency = frappe.defaults.get_global_default('currency')
    credits_balance = get_user_credits_balance()
    
    # Format the balance with currency
    context.formatted_balance = fmt_money(credits_balance, currency=currency)

    context.title = "Invoice2Erpnext Credits Balance"
 
    return context

def get_user_credits_balance():
    user = frappe.session.user
    credits_info = frappe.get_doc("Doc2Sys User Settings", {"user": user})
    if not credits_info:
        return _("User settings not found")
    
    return credits_info.credits or 0
