import frappe
from frappe.model.document import Document
import json

class Doc2SysIntegrationLog(Document):
    def before_insert(self):
        """Ensure data is stored as proper JSON"""
        if self.data and isinstance(self.data, (dict, list)):
            self.data = json.dumps(self.data, indent=2)
    
    def get_parsed_data(self):
        """Return parsed JSON data"""
        if not self.data:
            return None
            
        try:
            return json.loads(self.data)
        except:
            return self.data
    
    @frappe.whitelist()
    def retry_integration(self):
        """Retry a failed integration"""
        if self.status != "error":
            frappe.throw("Only failed integrations can be retried")
            
        from doc2sys.integrations.registry import IntegrationRegistry
        
        try:
            # Get the original document data
            data = self.get_parsed_data()
            if not data or not data.get("doc_name"):
                frappe.throw("Cannot retry: Missing original document reference")
                
            # Get the original document
            doc_name = data.get("doc_name")
            doc = frappe.get_doc("Doc2Sys Item", doc_name)
            
            # Get integration settings
            settings_list = frappe.get_all(
                "Doc2Sys Integration Settings",
                filters={"integration_type": self.integration, "enabled": 1},
                fields=["name"]
            )
            
            if not settings_list:
                frappe.throw(f"No enabled settings found for {self.integration}")
                
            settings = frappe.get_doc("Doc2Sys Integration Settings", settings_list[0].name)
            
            # Create integration instance and retry
            integration = IntegrationRegistry.create_instance(
                self.integration,
                settings=settings.as_dict()
            )
            
            result = integration.sync_document(doc.as_dict())
            
            if result.get("success"):
                return {"status": "success", "message": "Integration retried successfully"}
            else:
                return {"status": "error", "message": result.get("message")}
                
        except Exception as e:
            frappe.log_error(f"Retry failed: {str(e)}", "Integration Retry Error")
            return {"status": "error", "message": str(e)}