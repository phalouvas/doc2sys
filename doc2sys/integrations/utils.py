import frappe
import json
import requests
from typing import Dict, Any, Optional, List

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

# UPDATED: Refactored to avoid circular imports
def process_integrations(doc2sys_item: Dict[str, Any]) -> Dict[str, Any]:
    """Process all enabled integrations for a Doc2Sys Item"""
    # Import here to avoid circular imports
    from doc2sys.integrations.registry import get_integration_class
    
    if not doc2sys_item:
        return {"success": False, "message": "No document provided"}
    
    # Get the document name for reference
    doc_name = doc2sys_item.get("name")
    user = doc2sys_item.get("user")
    
    # Get all enabled integrations for the user
    enabled_integrations = get_enabled_integrations(user)
    
    if not enabled_integrations:
        return {
            "success": False, 
            "message": "No enabled integrations found for this user"
        }
    
    # Initialize results
    results = {
        "success": True,
        "message": "Integration processing completed",
        "integration_results": []
    }
    
    # Flag to track if all integrations succeeded
    all_succeeded = True
    
    # Process each integration
    for integration_settings in enabled_integrations:
        integration_name = integration_settings.get("integration_type")
        
        try:
            # Get the integration class
            integration_class = get_integration_class(integration_name)
            if not integration_class:
                error_msg = f"Integration type '{integration_name}' not found"
                frappe.log_error(error_msg, f"[{integration_name}] Integration not found")
                results["integration_results"].append({
                    "integration": integration_name,
                    "success": False,
                    "message": error_msg
                })
                all_succeeded = False
                continue
            
            # Initialize the integration with user settings
            integration = integration_class(integration_settings)
            
            # Sync the document using the integration
            sync_result = integration.sync_document(doc2sys_item)
            
            # Add the result to our results list
            results["integration_results"].append({
                "integration": integration_name,
                "success": sync_result.get("success", False),
                "message": sync_result.get("message", ""),
                "data": sync_result.get("data", {})
            })
            
            # Update the overall success flag
            if not sync_result.get("success", False):
                all_succeeded = False
                
        except Exception as e:
            error_msg = f"Error processing integration: {str(e)}"
            frappe.log_error(
                error_msg, 
                f"[{integration_name}] Error processing integration | User: {user} | Ref: {doc_name}"
            )
            
            results["integration_results"].append({
                "integration": integration_name,
                "success": False,
                "message": error_msg
            })
            
            all_succeeded = False
    
    # Update the overall success flag
    results["success"] = all_succeeded
    
    return results

def get_enabled_integrations(user: str) -> List[Dict[str, Any]]:
    """Get all enabled integrations for a user"""
    if not user:
        return []
    
    # Get all integration settings for the user
    user_settings = frappe.get_all(
        "Doc2Sys User Settings",
        filters={"user": user, "integration_enabled": 1},
        fields=["*"]
    )
    
    return user_settings