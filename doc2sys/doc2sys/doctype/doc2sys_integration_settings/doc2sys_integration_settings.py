import frappe
from frappe.model.document import Document
from doc2sys.integrations.registry import IntegrationRegistry

class Doc2SysIntegrationSettings(Document):
    
    def before_save(self):
        """Process field mapping JSON if it's provided as a string"""
        if isinstance(self.field_mapping, str):
            try:
                import json
                json.loads(self.field_mapping)  # Just validate it's valid JSON
            except Exception:
                frappe.throw("Field Mapping must be a valid JSON object")
    
    @frappe.whitelist()
    def test_connection(self):
        """Test the connection to the integration"""
        try:
            # Create integration instance
            integration = IntegrationRegistry.create_instance(
                self.integration_type, 
                settings=self.as_dict()
            )
            
            # Test connection
            result = integration.test_connection()
            
            if result.get("success"):
                return {"status": "success", "message": result.get("message")}
            else:
                return {"status": "error", "message": result.get("message")}
                
        except Exception as e:
            frappe.log_error(f"Connection test failed: {str(e)}", "Integration Error")
            return {"status": "error", "message": str(e)}
    
    @frappe.whitelist()
    def get_mapping_fields(self):
        """Get available mapping fields for this integration"""
        try:
            integration = IntegrationRegistry.create_instance(
                self.integration_type,
                settings=self.as_dict()
            )
            
            return integration.get_mapping_fields()
            
        except Exception as e:
            frappe.log_error(f"Failed to get mapping fields: {str(e)}", "Integration Error")
            return []