import frappe
from doc2sys.integrations.registry import IntegrationRegistry
from doc2sys.integrations.utils import create_integration_log  # Add this import

def trigger_integrations_on_insert(doc, method=None, is_manual=False):
    """Trigger integrations when a new Doc2Sys Item is created"""
    if isinstance(doc, str):
        doc = frappe.get_doc(frappe.parse_json(doc))
        is_manual = True
    _process_integrations(doc, is_manual)

@frappe.whitelist()
def trigger_integrations_on_update(doc, method=None, is_manual=False):
    """Trigger integrations when a Doc2Sys Item is updated"""
    if isinstance(doc, str):
        doc = frappe.get_doc(frappe.parse_json(doc))
        is_manual = True
    _process_integrations(doc, is_manual)

def _process_integrations(doc, is_manual=False):
    """Process all enabled integrations for the document"""
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
        fields=["name", "user"]
    )
    
    if not user_settings_list:
        frappe.log_error(
            f"No settings found for user {document_user}, cannot process integrations for document {doc.name}",
            "Doc2Sys Integration Error"
        )
        return
    
    # There should only be one settings document per user
    settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings_list[0].name)
    
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
                    document=doc.name  # Add this line
                )
            else:
                # Log successful integrations as well
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
                    document=doc.name  # Add this line
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