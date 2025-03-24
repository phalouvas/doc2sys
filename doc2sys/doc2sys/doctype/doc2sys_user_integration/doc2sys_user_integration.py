import frappe
from frappe.model.document import Document
from doc2sys.integrations.registry import IntegrationRegistry

class Doc2SysUserIntegration(Document):
    
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
    