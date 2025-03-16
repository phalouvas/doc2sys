import frappe
import requests
from typing import Dict, Any, List

from doc2sys.integrations.base import BaseIntegration
from doc2sys.integrations.registry import register_integration
from doc2sys.integrations.utils import map_document_fields

@register_integration
class ERPNextIntegration(BaseIntegration):
    """Integration with another ERPNext instance"""
    
    def authenticate(self) -> bool:
        """Authenticate with ERPNext using API key and secret"""
        try:
            api_key = self.settings.get("api_key")
            api_secret = frappe.utils.password.get_decrypted_password("Doc2Sys Integration Settings", self.settings.name, "api_secret") or ""
            base_url = self.settings.get("base_url")
            
            if not (api_key and api_secret and base_url):
                return False
                
            # Test authentication by fetching a simple endpoint
            response = requests.get(
                f"{base_url}/api/method/frappe.auth.get_logged_user",
                headers={
                    "Authorization": f"token {api_key}:{api_secret}"
                }
            )
            
            if response.status_code == 200:
                self.is_authenticated = True
                return True
            return False
        except Exception as e:
            self.log_activity("error", f"Authentication failed: {str(e)}")
            return False
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to ERPNext instance"""
        if self.authenticate():
            return {"success": True, "message": "Connection established successfully"}
        return {"success": False, "message": "Failed to connect to ERPNext instance"}
    
    def sync_document(self, doc2sys_item: Dict[str, Any]) -> Dict[str, Any]:
        """Sync a doc2sys_item to the external ERPNext system"""
        if not self.is_authenticated and not self.authenticate():
            return {"success": False, "message": "Authentication failed"}
            
        try:
            # Get the field mapping from settings
            field_mapping = self.settings.get("field_mapping", {})
            if not field_mapping:
                field_mapping = {
                    "title": "title",
                    "description": "description",
                    "document_type": "document_type",
                    "extracted_data": "extracted_data"
                }
                
            # Map the fields
            mapped_data = map_document_fields(doc2sys_item, field_mapping)
            mapped_data["doctype"] = self.settings.get("target_doctype", "Doc2Sys Item")
            
            # Send to ERPNext
            api_key = self.settings.get("api_key")
            api_secret = frappe.utils.password.get_decrypted_password("Doc2Sys Integration Settings", self.settings.name, "api_secret") or ""
            base_url = self.settings.get("base_url")
            
            response = requests.post(
                f"{base_url}/api/resource/{mapped_data['doctype']}",
                json=mapped_data,
                headers={
                    "Authorization": f"token {api_key}:{api_secret}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code in (200, 201):
                result = response.json()
                self.log_activity("success", f"Document synced successfully", 
                                 {"doc_name": result.get("data", {}).get("name")})
                return {"success": True, "data": result}
            else:
                self.log_activity("error", f"Failed to sync document: {response.text}")
                return {"success": False, "message": response.text}
        except Exception as e:
            self.log_activity("error", f"Sync error: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def get_mapping_fields(self) -> List[Dict[str, Any]]:
        """Return a list of fields available for mapping in ERPNext"""
        return [
            {"field": "title", "label": "Title", "type": "Data"},
            {"field": "description", "label": "Description", "type": "Text"},
            {"field": "document_type", "label": "Document Type", "type": "Data"},
            {"field": "extracted_data", "label": "Extracted Data", "type": "JSON"},
            {"field": "status", "label": "Status", "type": "Select"},
        ]