import frappe
from frappe.model.document import Document
import json
from doc2sys.integrations.utils import create_integration_log  # Add this import

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
            
            # Determine which user and integration to use
            user = self.user or frappe.session.user
            integration_reference = self.integration_reference
            
            # Get user settings
            user_settings_list = frappe.get_list(
                "Doc2Sys User Settings", 
                filters={"user": user},
                fields=["name"]
            )
            
            if not user_settings_list:
                frappe.throw(f"No settings found for user {user}")
                
            user_settings = frappe.get_doc("Doc2Sys User Settings", user_settings_list[0].name)
            
            # Find the correct integration
            integration = None
            
            # First try by integration_reference if available
            if integration_reference:
                for integ in user_settings.user_integrations:
                    if integ.name == integration_reference and integ.integration_type == self.integration:
                        integration = integ
                        break
                        
            # If not found, try by integration_type
            if not integration:
                for integ in user_settings.user_integrations:
                    if integ.integration_type == self.integration and integ.enabled:
                        integration = integ
                        break
                        
            if not integration:
                frappe.throw(f"No enabled {self.integration} integration found for user {user}")
                
            # Create integration instance with the found settings
            integration_settings = integration.as_dict()
            # Add parent reference for password retrieval
            integration_settings['parent'] = user_settings.name
            
            integration_instance = IntegrationRegistry.create_instance(
                self.integration,
                settings=integration_settings
            )
            
            # When logging new attempts, include document reference
            create_integration_log(
                integration_type=self.integration_type,
                status="info",
                message="Retrying integration...",
                data=data,
                user=user,
                integration_reference=integration_reference,
                document=self.document  # Include document reference in retry logs
            )
            
            result = integration_instance.sync_document(doc.as_dict())
            
            if result.get("success"):
                return {"status": "success", "message": "Integration retried successfully"}
            else:
                return {"status": "error", "message": result.get("message")}
                
        except Exception as e:
            frappe.log_error(f"Retry failed: {str(e)}", "Integration Retry Error")
            return {"status": "error", "message": str(e)}

@frappe.whitelist()
def retry_integration(log_name):
    """Retry an integration from its log entry"""
    try:
        log = frappe.get_doc("Doc2Sys Integration Log", log_name)
        return log.retry_integration()
    except Exception as e:
        frappe.log_error(f"Retry failed: {str(e)}", "Integration Retry Error")
        return {"status": "error", "message": str(e)}