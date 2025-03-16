import frappe
from doc2sys.integrations.registry import IntegrationRegistry

def trigger_integrations_on_insert(doc, method=None):
    """Trigger integrations when a new Doc2Sys Item is created"""
    _process_integrations(doc)

@frappe.whitelist()
def trigger_integrations_on_update(doc, method=None):
    """Trigger integrations when a Doc2Sys Item is updated"""
    if isinstance(doc, str):
        doc = frappe.get_doc(frappe.parse_json(doc))
    _process_integrations(doc)

def _process_integrations(doc):
    """Process all enabled integrations for the document"""
    if doc.doctype != "Doc2Sys Item" or not doc.extracted_data:
        return
        
    # Discover available integrations
    IntegrationRegistry.discover_integrations()
    
    # Get all enabled integration settings
    settings_list = frappe.get_all(
        "Doc2Sys Integration Settings", 
        filters={"enabled": 1, "auto_sync": 1},
        fields=["name", "integration_type"]
    )
    
    for settings_doc in settings_list:
        try:
            # Get complete settings
            settings = frappe.get_doc("Doc2Sys Integration Settings", settings_doc.name)
            
            # Create integration instance
            integration_instance = IntegrationRegistry.create_instance(
                settings_doc.integration_type,
                settings=settings.as_dict()
            )
            
            # Sync the document
            result = integration_instance.sync_document(doc.as_dict())
            
            if not result.get("success"):
                frappe.log_error(
                    f"Integration failed: {result.get('message')}",
                    f"Doc2Sys Integration: {settings_doc.integration_type}"
                )
        except Exception as e:
            frappe.log_error(
                f"Error processing integration {settings_doc.integration_type}: {str(e)}",
                "Doc2Sys Integration Error"
            )