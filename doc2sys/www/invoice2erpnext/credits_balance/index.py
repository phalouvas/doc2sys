import frappe
from frappe import _ 
from frappe.utils import fmt_money

def get_context(context):
    # Get the system default currency
    currency = frappe.defaults.get_global_default('currency')
    credits_balance = get_user_credits_balance()
    
    # Format the balance with currency
    context.formatted_balance = fmt_money(credits_balance, currency=currency)

    context.no_cache = 1
    context.show_sidebar = True
 
    return context

def get_user_credits_balance():
    user = frappe.session.user
    try:
        credits_info = frappe.get_doc("Doc2Sys User Settings", {"user": user})
        return credits_info.credits or 0
    except frappe.DoesNotExistError:
        return _("User settings not found")
    except Exception as e:
        frappe.log_error(f"Error fetching credits balance: {str(e)}")
        return _("Error fetching credits balance")
