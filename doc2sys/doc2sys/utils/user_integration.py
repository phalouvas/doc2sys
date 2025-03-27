import frappe

def create_user_settings(doc, method=None):
    """
    Create Doc2Sys User Settings for a new user with initial credits
    and LLM settings from Doc2Sys Settings
    """
    # Skip if it's not a regular user
    if doc.user_type not in ("System User", "Website User"):
        return
    
    # Check if settings already exist for this user
    existing_settings = frappe.get_all(
        "Doc2Sys User Settings", 
        filters={"user": doc.name}
    )
    
    # If settings already exist, don't create a new one
    if existing_settings:
        return
    
    # Get default settings from Doc2Sys Settings
    default_settings = {}
    try:
        doc2sys_settings = frappe.get_single("Doc2Sys Settings")
        
        # Get default values
        default_settings = {
            "credits": doc2sys_settings.credits or 0,
            "llm_provider": doc2sys_settings.llm_provider,
            "azure_endpoint": doc2sys_settings.azure_endpoint,
            "azure_key": doc2sys_settings.azure_key,
            "azure_model": doc2sys_settings.azure_model,
            "cost_prebuilt_invoice_per_page": doc2sys_settings.cost_prebuilt_invoice_per_page
        }
    except Exception as e:
        frappe.log_error(
            f"Error getting default settings from Doc2Sys Settings: {str(e)}",
            "User Settings Creation Error"
        )
    
    # Create new Doc2Sys User Settings
    try:
        user_settings = frappe.new_doc("Doc2Sys User Settings")
        user_settings.user = doc.name
        
        # Set default values from Doc2Sys Settings
        for field, value in default_settings.items():
            if value is not None:
                user_settings.set(field, value)
        
        user_settings.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.msgprint(f"Created Doc2Sys User Settings for {doc.name} with {default_settings.get('credits', 0)} credits")
    except Exception as e:
        frappe.log_error(
            f"Error creating Doc2Sys User Settings for user {doc.name}: {str(e)}",
            "User Settings Creation Error"
        )