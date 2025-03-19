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
    """Create an integration log entry"""
    try:
        # Ensure integration_type is always provided
        if not integration_type:
            integration_type = "Unknown"  # Provide a default value
        
        # Extract document reference from data if not explicitly provided
        if not document and isinstance(data, dict) and data.get("doc_name"):
            document = data.get("doc_name")
        
        # Convert data to JSON string if it's a dict/list
        if data and isinstance(data, (dict, list)):
            data = json.dumps(data)
            
        log = frappe.get_doc({
            "doctype": "Doc2Sys Integration Log",
            "integration_type": integration_type,
            "status": status,
            "message": message,
            "data": data,
            "user": user,
            "integration_reference": integration_reference,
            "document": document
        })
        
        log.insert(ignore_permissions=True)
        return log.name
    except Exception as e:
        # Fallback to system log if integration log creation fails
        frappe.log_error(
            f"Failed to create integration log: {str(e)}\n"
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
    
    # Find the matching integration
    for integ in user_settings.user_integrations:
        # Skip disabled integrations if enabled_only is True
        if enabled_only and not integ.enabled:
            continue
            
        # Match by reference if provided
        if integration_reference and integ.name == integration_reference:
            integration_dict = integ.as_dict()
            integration_dict['parent'] = user_settings.name
            return integration_dict, user_settings.name
            
        # Match by type if provided and reference didn't match
        if integration_type and integ.integration_type == integration_type:
            integration_dict = integ.as_dict()
            integration_dict['parent'] = user_settings.name
            return integration_dict, user_settings.name
            
    # No matching integration found
    return None, user_settings.name
