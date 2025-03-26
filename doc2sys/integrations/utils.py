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
            data = json.dumps(data, ensure_ascii=False)
            
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
    
    # Log how many integrations are available vs how many are enabled
    total_integrations = len(settings_doc.user_integrations)
    enabled_integrations = sum(1 for i in settings_doc.user_integrations if i.enabled)
    
    frappe.logger().debug(
        f"Processing integrations for document {doc.name}: {enabled_integrations} enabled out of {total_integrations} total"
    )
    
    # Process each enabled integration for this user
    for integration in settings_doc.user_integrations:
        # Skip disabled integrations
        if integration.enabled != 1:  # Explicitly check for 1 (enabled)
            frappe.logger().debug(f"Skipping disabled integration: {integration.integration_type} ({integration.name})")
            continue
            
        # Log which integration we're processing
        frappe.logger().info(f"Processing integration {integration.integration_type} ({integration.name}) for document {doc.name}")
        
        try:
            # Create integration instance with user context
            integration_settings = integration.as_dict()
            integration_settings['parent'] = settings_doc.name
            integration_settings['user'] = settings_doc.user
            
            integration_instance = IntegrationRegistry.create_instance(
                integration.integration_type,
                settings=integration_settings
            )
            
                        # Sync the document
            result = integration_instance.sync_document(doc.as_dict())
            
            if not result.get("success"):
                create_integration_log(
                    integration.integration_type,
                    "error",
                    f"Integration failed: {result.get('message')}",
                    data={
                        "doc_name": doc.name,
                        "error": result.get('message')
                    },
                    user=settings_doc.user,
                    integration_reference=integration.name,
                    document=doc.name
                )
            else:
                # Log successful integrations
                create_integration_log(
                    integration.integration_type,
                    "success",
                    "Integration processed successfully",
                    data={
                        "doc_name": doc.name,
                        "result": result.get('data', {})
                    },
                    user=settings_doc.user,
                    integration_reference=integration.name,
                    document=doc.name
                )
                
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
                integration.integration_type,
                "error",
                f"Error processing integration: {str(e)}",
                data={
                    "doc_name": doc.name,
                    "error": str(e)
                },
                user=settings_doc.user,
                integration_reference=integration.name,
                document=doc.name  # Add the direct document reference
            )