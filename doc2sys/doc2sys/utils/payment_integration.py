import frappe

def update_user_credits(payment_entry, method):
    """
    Increase user credits when a customer payment entry is submitted for credit items
    """
    # Only process if this is a payment receipt (not a payment made)
    if payment_entry.payment_type != "Receive":
        return
    
    # Only process customer payments
    if payment_entry.party_type != "Customer":
        return
    
    # Check if payment entry has references to sales invoices
    if not payment_entry.references or len(payment_entry.references) == 0:
        return
    
    # Get credits item from Doc2Sys Settings
    doc2sys_settings = frappe.get_doc("Doc2Sys Settings", "Doc2Sys Settings")
    if not doc2sys_settings.credits_item:
        frappe.log_error(
            "Credits item not configured in Doc2Sys Settings",
            "Payment Credit Update Error"
        )
        return
    
    credits_item = doc2sys_settings.credits_item
    has_credits_item = False
    
    # Check if any of the referenced sales invoices contain the credits item
    for ref in payment_entry.references:
        if ref.reference_doctype != "Sales Invoice":
            continue
            
        sales_invoice = frappe.get_doc("Sales Invoice", ref.reference_name)
        
        # Check if any items in this invoice match the credits item
        for item in sales_invoice.items:
            if item.item_code == credits_item:
                has_credits_item = True
                break
                
        if has_credits_item:
            break
    
    # If no credits item was found in any invoice, don't update credits
    if not has_credits_item:
        return
    
    customer = payment_entry.party
    payment_amount = payment_entry.paid_amount
    
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
    frappe.db.set_value("Doc2Sys User Settings", user_setting.name, "credits", new_credits)
    
    # Display the message
    frappe.msgprint(f"Your credits updated: {current_credits} → {new_credits}")

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
