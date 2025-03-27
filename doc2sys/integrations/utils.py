import frappe
import json
import requests
from typing import Dict, Any, Optional

def execute_webhook(url: str, data: Dict[str, Any], 
                   headers: Optional[Dict[str, str]] = None, 
                   method: str = "POST") -> Dict[str, Any]:
    """Execute a webhook to an external system"""
    try:
        headers = headers or {"Content-Type": "application/json"}
        
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers)
        else:
            response = requests.get(url, params=data, headers=headers)
            
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_integration_log(integration_type, status, message, data=None, user=None, integration_reference=None, document=None):
    """Create a log entry using Frappe's logging system"""
    try:
        # Ensure integration_type is always provided
        if not integration_type:
            integration_type = "Unknown"
        
        # Format data for logging
        log_data = ""
        if data:
            if isinstance(data, (dict, list)):
                log_data = json.dumps(data, ensure_ascii=False)
            else:
                log_data = str(data)
        
        # Build log message
        log_message = f"[{integration_type}] {message}"
        if user:
            log_message += f" | User: {user}"
        if integration_reference:
            log_message += f" | Ref: {integration_reference}"
        if document:
            log_message += f" | Doc: {document}"
        if log_data:
            log_message += f" | Data: {log_data}"
        
        # Log based on status
        if status.lower() == "error":
            frappe.log_error(log_message, f"Integration {status.title()}")
        elif status.lower() == "warning":
            frappe.logger().warning(log_message)
        elif status.lower() == "success":
            frappe.logger().info(log_message)
        else:
            frappe.logger().debug(log_message)
            
        return f"{integration_type}_{status}"  # Return a reference ID for compatibility
    except Exception as e:
        # Final fallback
        frappe.log_error(
            f"Failed to create log: {str(e)}\n"
            f"Original info: {integration_type} - {status} - {message}",
            "Integration Log Error"
        )
        return None

# Add another helper function

def find_user_integration(user, integration_type=None, integration_reference=None, enabled_only=True):
    """
    Find a user integration
    
    Args:
        user: User to find integrations for
        integration_type: Type of integration to find
        integration_reference: Specific integration reference ID
        enabled_only: Only return enabled integrations
        
    Returns:
        Tuple of (integration dict, user_settings name)
    """
    # Get user settings
    user_settings_list = frappe.get_list(
        "Doc2Sys User Settings", 
        filters={"user": user},
        fields=["name"]
    )
    
    if not user_settings_list:
        return None, None
        
    user_settings = frappe.get_doc("Doc2Sys User Settings", user_settings_list[0].name)
    
    # Check if integration is enabled (if enabled_only)
    if enabled_only and not user_settings.get("integration_enabled", 0):
        return None, user_settings.name
    
    # If integration_type is specified, check if it matches
    if integration_type and user_settings.get("integration_type") != integration_type:
        return None, user_settings.name
    
    # Integration settings now directly in user_settings
    if user_settings.get("integration_type"):
        # Create a dict with the integration settings
        integration_dict = {
            "integration_type": user_settings.integration_type,
            "enabled": user_settings.get("integration_enabled", 0),
            "name": user_settings.name,  # Use the user settings name as the integration reference
            "parent": user_settings.name,
            # Add any other fields that are needed
        }
        
        # Add all integration-specific fields from user_settings
        # This assumes field names are consistent between old and new structure
        for field in ["api_key", "api_secret", "base_url", "webhook_url"]:
            if user_settings.get(field):
                integration_dict[field] = user_settings.get(field)
                
        return integration_dict, user_settings.name
            
    # No matching integration found
    return None, user_settings.name

@frappe.whitelist()
def process_integrations(doc):
    """Process all enabled integrations for the document"""
    
    from doc2sys.integrations.registry import IntegrationRegistry

    if isinstance(doc, str):
        doc = frappe.get_doc(frappe.parse_json(doc))
        
    if doc.doctype != "Doc2Sys Item" or not doc.extracted_data:
        return
        
    # Discover available integrations
    IntegrationRegistry.discover_integrations()
    
    # Get the document's user - only process integrations for this user
    document_user = doc.user
    
    if not document_user:
        frappe.log_error(
            f"Doc2Sys Item {doc.name} has no user assigned, cannot process integrations",
            "Doc2Sys Integration Error"
        )
        return
    
    # Get settings for the document's user only
    user_settings_list = frappe.get_all(
        "Doc2Sys User Settings",
        filters={"user": document_user},
        fields=["name", "user", "credits"]
    )
    
    if not user_settings_list:
        frappe.log_error(
            f"No settings found for user {document_user}, cannot process integrations for document {doc.name}",
            "Doc2Sys Integration Error"
        )
        return
    
    # There should only be one settings document per user
    settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings_list[0].name)

    if settings_doc.credits < doc.cost:
        frappe.logger().info(
            f"Skipping integrations for document {doc.name} due to insufficient credits ({settings_doc.credits} available, {doc.cost} required)"
        )
        raise frappe.ValidationError("Insufficient credits to process integrations")
        return
    
    # Check if there is an integration configured
    has_integration = settings_doc.get("integration_type") is not None
    is_enabled = settings_doc.get("integration_enabled", 0) == 1
    
    frappe.logger().debug(
        f"Processing integrations for document {doc.name}: Integration is {'enabled' if is_enabled else 'disabled'}"
    )
    
    # Skip if no integration or not enabled
    if not has_integration or not is_enabled:
        frappe.logger().debug(f"No enabled integration found for user {document_user}")
        return
    
    # Log which integration we're processing
    frappe.logger().info(f"Processing integration {settings_doc.integration_type} for document {doc.name}")
    
    try:
        # Create integration instance with user context
        integration_settings = settings_doc.as_dict()
        
        integration_instance = IntegrationRegistry.create_instance(
            settings_doc.integration_type,
            settings=integration_settings
        )
        
        # Sync the document
        result = integration_instance.sync_document(doc.as_dict())
        
        if not result.get("success"):
            create_integration_log(
                settings_doc.integration_type,
                "error",
                f"Integration failed: {result.get('message')}",
                data={
                    "doc_name": doc.name,
                    "error": result.get('message')
                },
                user=settings_doc.user,
                integration_reference=settings_doc.name,
                document=doc.name
            )
        else:
            # Update the document status
            doc.db_set('status', "Completed", update_modified=False)
            
            # Deduct credits after successful integration
            # Get current credits and calculate new value
            current_credits = settings_doc.credits
            new_credits = current_credits - doc.cost
            
            # Update the credits in the database
            frappe.db.set_value("Doc2Sys User Settings", settings_doc.name, "credits", new_credits)
            frappe.db.commit()  # Ensure the change is committed
            
            # Log the credit deduction
            frappe.logger().info(
                f"Deducted {doc.cost} credits from user {settings_doc.user}. " +
                f"New balance: {new_credits}"
            )
            
    except Exception as e:
        create_integration_log(
            settings_doc.integration_type,
            "error",
            f"Error processing integration: {str(e)}",
            data={
                "doc_name": doc.name,
                "error": str(e)
            },
            user=settings_doc.user,
            integration_reference=settings_doc.name,
            document=doc.name
        )