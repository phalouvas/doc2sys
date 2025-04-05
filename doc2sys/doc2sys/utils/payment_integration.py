import frappe
from frappe import _

def update_user_credits(payment_entry, method):
    """
    Increase user credits when a customer payment entry is submitted for credit items
    """
    # Store original permission flag
    original_ignore_perms = frappe.flags.ignore_permissions
    
    try:
        # Only process if this is a payment receipt (not a payment made)
        if payment_entry.payment_type != "Receive":
            return
        
        # Only process customer payments
        if payment_entry.party_type != "Customer":
            return
        
        # Check if payment entry has references to sales invoices
        if not payment_entry.references or len(payment_entry.references) == 0:
            return
        
        # Get credit settings from Doc2Sys Settings
        try:
            doc2sys_settings = frappe.get_doc("Doc2Sys Settings", "Doc2Sys Settings")
            if not doc2sys_settings.credits_item_group:
                frappe.log_error(
                    "Credits item group not configured in Doc2Sys Settings",
                    "Payment Credit Update Error"
                )
                return
        except Exception as e:
            frappe.log_error(
                f"Error retrieving Doc2Sys Settings: {str(e)}",
                "Payment Credit Update Error"
            )
            return
            
        credits_item_group = doc2sys_settings.credits_item_group
        total_credits_to_add = 0
        
        # Calculate credits based on net amount of items from the credits item group
        for ref in payment_entry.references:
            if ref.reference_doctype not in ["Sales Invoice", "Sales Order"]:
                continue
                
            reference_doc = frappe.get_doc(ref.reference_doctype, ref.reference_name)
            invoice_credit_items_total = 0
            
            # Sum up net amount of credit items in this invoice or order
            for item in reference_doc.items:
                item_doc = frappe.get_doc("Item", item.item_code)
                if item_doc.item_group == credits_item_group:
                    invoice_credit_items_total += item.net_amount
            
            # If this document has credit items, calculate the portion being paid
            if invoice_credit_items_total > 0:
                # Calculate what percentage of the document is being paid with this payment
                payment_percentage = min(ref.allocated_amount / reference_doc.grand_total, 1.0)
                # Add the corresponding portion of credit items to the total
                total_credits_to_add += invoice_credit_items_total * payment_percentage
        
        # If no credits to add, don't proceed
        if total_credits_to_add <= 0:
            return
        
        customer = payment_entry.party
        payment_amount = total_credits_to_add  # Use calculated net amount instead of paid_amount
        
        # Find the user linked to this customer
        customer = frappe.get_doc("Customer", customer)
        if not customer:
            frappe.log_error(
                f"Cannot find customer {customer}",
                "Payment Credit Update Error"
            )
            return
        
        if not customer.portal_users:
            frappe.log_error(
                f"No portal users found for customer {customer}",
                "Payment Credit Update Error"
            )
            return
        
        user = customer.portal_users[0].user
        
        if not user:
            frappe.log_error(
                f"Cannot find user for customer {customer}",
                "Payment Credit Update Error"
            )
            return
        
        # Find the user settings for this user
        user_settings = frappe.get_all(
            "Doc2Sys User Settings", 
            filters={"user": user},
            fields=["name", "credits"]
        )
        
        if not user_settings:
            frappe.log_error(
                f"No Doc2Sys User Settings found for user {user} (customer {customer})",
                "Payment Credit Update Error"
            )
            return
        
        # Get the user setting (there should be only one per user)
        user_setting = user_settings[0]
        
        # Get the current credits value
        current_credits = user_setting.credits or 0
        new_credits = current_credits + payment_amount
        
        # Update the credits using standard database update
        try:
            frappe.db.set_value("Doc2Sys User Settings", user_setting.name, "credits", new_credits)
            frappe.msgprint(f"Your credits updated: {current_credits} → {new_credits}")
        except Exception as e:
            frappe.log_error(
                f"Failed to update credits for user {user}: {str(e)}",
                "Payment Credit Update Error"
            )
            
    except Exception as e:
        # Catch any unexpected exceptions
        frappe.log_error(
            f"Unexpected error in update_user_credits for payment {payment_entry.name}: {str(e)}",
            "Payment Credit Update Error"
        )
        # Optionally re-raise if you want the payment to fail when credits can't be updated
        # raise
    finally:
        # Always restore the original permission flag when function exits
        frappe.flags.ignore_permissions = original_ignore_perms

def deduct_user_credits(user, amount, doc_reference=None):
    """
    Deduct credits from user's balance after document processing
    
    Args:
        user (str): The user to deduct credits from
        amount (float): The amount to deduct
        doc_reference (str, optional): Reference to the document being processed
    
    Returns:
        float: New credit balance or None if error
    """
    if not user or not amount or amount <= 0:
        return None
    
    # Find the user settings for this user
    user_settings = frappe.get_all(
        "Doc2Sys User Settings", 
        filters={"user": user},
        fields=["name", "credits"]
    )
    
    if not user_settings:
        frappe.log_error(
            f"No Doc2Sys User Settings found for user {user}",
            "Credit Deduction Error"
        )
        return None
    
    # Get the user setting (there should be only one per user)
    user_setting = user_settings[0]
    
    # Get the current credits value
    current_credits = user_setting.credits or 0
    new_credits = max(0, current_credits - amount)  # Don't allow negative credits
    
    # Update the credits using standard database update
    frappe.db.set_value("Doc2Sys User Settings", user_setting.name, "credits", new_credits)
    
    return new_credits
