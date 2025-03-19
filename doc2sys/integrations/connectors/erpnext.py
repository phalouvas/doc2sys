import frappe
import requests
import json
from typing import Dict, Any, List

from doc2sys.integrations.base import BaseIntegration
from doc2sys.integrations.registry import register_integration

@register_integration
class ERPNextIntegration(BaseIntegration):
    """Integration with another ERPNext instance"""
    
    def authenticate(self) -> bool:
        """Authenticate with ERPNext using API key and secret"""
        try:
            # Get credentials from settings
            api_key = self.settings.get("api_key")
            base_url = self.settings.get("base_url")
            
            # Get the name of the integration record
            doc_name = self.settings.get("name")
            
            # Get decrypted password using just the row name (without parent prefix)
            api_secret = ""
            if doc_name:
                try:
                    api_secret = frappe.utils.password.get_decrypted_password(
                        "Doc2Sys User Integration", doc_name, "api_secret"
                    ) or ""
                except Exception as e:
                    self.log_activity("error", f"Failed to get password: {str(e)}")
            
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
        try:
            # Extract and parse mapped data from the extracted_data field
            extracted_data = doc2sys_item.get("extracted_data", "{}")
            
            # Check if extracted_data is a valid JSON string
            try:
                mapped_data = json.loads(extracted_data)
            except json.JSONDecodeError:
                self.log_activity("error", "Invalid JSON in extracted_data")
                return {"success": False, "message": "Invalid JSON in extracted_data"}
            
            # Verify integration type
            if mapped_data.get("integration_type") != "ERPNextIntegration":
                self.log_activity("error", "Invalid integration type. Expected ERPNextIntegration.")
                return {"success": False, "message": "Invalid integration type"}
                
            # Get API credentials
            api_key = self.settings.get("api_key")
            doc_name = self.settings.get("name")
            
            # Get decrypted password using just the row name (without parent prefix)
            api_secret = ""
            if doc_name:
                try:
                    api_secret = frappe.utils.password.get_decrypted_password(
                        "Doc2Sys User Integration", doc_name, "api_secret"
                    ) or ""
                except Exception as e:
                    self.log_activity("error", f"Failed to get password: {str(e)}")
                    return {"success": False, "message": f"Failed to retrieve API secret: {str(e)}"}
            
            base_url = self.settings.get("base_url")
            
            if not (api_key and api_secret and base_url):
                self.log_activity("error", "Missing required credentials")
                return {"success": False, "message": "Missing required credentials"}
                
            auth_headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json"
            }
            
            creation_order = mapped_data.get("creation_order", [])
            doctypes = mapped_data.get("doctypes", {})
            search_ids = mapped_data.get("search_id", {})
            
            created_documents = {}
            
            # Process doctypes in the specified order
            for doctype_name in creation_order:
                doctype_data = doctypes.get(doctype_name)
                search_id_field = search_ids.get(doctype_name)
                
                if not doctype_data or not search_id_field:
                    self.log_activity("error", f"Missing data or search field for {doctype_name}")
                    continue
                    
                # Handle both single objects and lists of objects
                if not isinstance(doctype_data, list):
                    doctype_data = [doctype_data]
                    
                doctype_results = []
                
                for item in doctype_data:
                    search_value = item.get(search_id_field)
                    if not search_value:
                        self.log_activity("error", f"Search value missing for {doctype_name}")
                        continue
                        
                    # Check if document exists
                    exists_response = requests.get(
                        f"{base_url}/api/method/frappe.client.get_list",
                        params={
                            "doctype": doctype_name,
                            "filters": json.dumps([[doctype_name, search_id_field, "=", search_value]]),
                            "fields": json.dumps(["name"])  # Ensure fields is a valid JSON string
                        },
                        headers=auth_headers
                    )
                    
                    document_exists = False
                    document_name = None
                    
                    if exists_response.status_code == 200:
                        results = exists_response.json().get("message", [])
                        if results and len(results) > 0:
                            document_exists = True
                            document_name = results[0].get("name")
                            self.log_activity("info", f"{doctype_name} already exists with {search_id_field}={search_value}")
                    
                    # Create document if it doesn't exist
                    if not document_exists:
                        # Add doctype to the item
                        item["doctype"] = doctype_name
                        
                        create_response = requests.post(
                            f"{base_url}/api/method/frappe.client.insert",
                            json={"doc": item},
                            headers=auth_headers
                        )
                        
                        if create_response.status_code in (200, 201):
                            result = create_response.json()
                            document_name = result.get("message", {}).get("name")
                            self.log_activity("success", f"Created {doctype_name} successfully", 
                                             {"doc_name": document_name})
                        else:
                            error_message = f"Failed to create {doctype_name}: {create_response.text}"
                            self.log_activity("error", error_message)
                            return {"success": False, "message": error_message}
                    
                    if document_name:
                        doctype_results.append(document_name)
                
                if doctype_results:
                    created_documents[doctype_name] = doctype_results
            
            return {"success": True, "data": created_documents}
            
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