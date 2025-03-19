import frappe
from doc2sys.integrations.registry import IntegrationRegistry

def trigger_integrations_on_insert(doc, method=None):
    """Trigger integrations when a new Doc2Sys Item is created"""
    _process_integrations(doc)

@frappe.whitelist()
def trigger_integrations_on_update(doc, method=None):
    """Trigger integrations when a Doc2Sys Item is updated"""
    is_manual = False
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
    
    # Get all users with settings
    user_settings_list = frappe.get_all(
        "Doc2Sys User Settings",
        fields=["name", "user"]
    )
    
    for user_settings in user_settings_list:
        try:
            # Get complete user settings
            settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings.name)
            
            # Process each enabled integration for this user
            for integration in settings_doc.user_integrations:
                if not integration.enabled:
                    continue
                    
                if not is_manual and not integration.auto_sync:
                    continue
                
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
                        from doc2sys.integrations.utils import create_integration_log
                        create_integration_log(
                            integration.integration_type,
                            "error",
                            f"Integration failed: {result.get('message')}",
                            data={
                                "doc_name": doc.name,
                                "error": result.get('message')
                            },
                            user=settings_doc.user,
                            integration_reference=integration.name
                        )
                        
                except Exception as e:
                    from doc2sys.integrations.utils import create_integration_log
                    create_integration_log(
                        integration.integration_type,
                        "error",
                        f"Error processing integration: {str(e)}",
                        data={
                            "doc_name": doc.name,
                            "error": str(e)
                        },
                        user=settings_doc.user,
                        integration_reference=integration.name
                    )
                    
        except Exception as e:
            frappe.log_error(
                f"Error processing integrations for user {user_settings.user}: {str(e)}",
                "Doc2Sys Integration Error"
            )