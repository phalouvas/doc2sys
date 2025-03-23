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
            # Add this line at the beginning of the method
            self.current_document = doc2sys_item.get("name")
            
            # Extract and parse mapped data from the extracted_data field
            extracted_data = doc2sys_item.get("extracted_data", "{}")
            
            # Check if extracted_data is a valid JSON string
            try:
                mapped_data = json.loads(extracted_data)
            except json.JSONDecodeError:
                self.log_activity("error", "Invalid JSON in extracted_data")
                return {"success": False, "message": "Invalid JSON in extracted_data"}
            
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
            
            # Get the items array from the mapped data
            items = mapped_data.get("items", [])
            
            if not items:
                self.log_activity("error", "No items found in the mapped data")
                return {"success": False, "message": "No items found in the mapped data"}
            
            created_documents = {}
            
            # Define doctype priorities - lower number = higher priority
            doctype_priority = {
                "Supplier": 1,
                "Item": 2,
                "Purchase Invoice": 3,
                # Add other doctypes as needed
            }
            
            # Sort items by doctype priority to ensure dependencies are created first
            sorted_items = sorted(items, key=lambda x: doctype_priority.get(x.get("doctype", ""), 999))
            
            # Process each item in priority order
            for item in sorted_items:
                doctype = item.get("doctype")
                
                if not doctype:
                    self.log_activity("error", f"Missing doctype in item")
                    return {"success": False, "message": "Missing doctype in item"}

                item = self.fix_payload(item)
                
                # Try to create the document directly without checking if it exists
                try:
                    create_response = requests.post(
                        f"{base_url}/api/method/frappe.client.insert",
                        json={"doc": item},
                        headers=auth_headers
                    )
                    
                    if create_response.status_code in (200, 201):
                        result = create_response.json()
                        document_name = result.get("message", {}).get("name")
                        
                        if doctype not in created_documents:
                            created_documents[doctype] = []
                        
                        created_documents[doctype].append(document_name)
                        self.log_activity("info", f"Created {doctype}: {document_name}")
                    else:
                        # Check if the error is because the document already exists
                        error_text = create_response.text
                        
                        if any(phrase in error_text.lower() for phrase in ["already exists", "duplicate", "duplicateentryerror"]):
                            # For documents that already exist, try to get their identifier
                            identifier = ""
                            if doctype == "Item":
                                identifier = item.get("item_code", "")
                            elif doctype == "Supplier":
                                identifier = item.get("supplier_name", "")
                            
                            self.log_activity("info", f"{doctype} {identifier} already exists, skipping")
                        else:
                            error_message = f"Failed to create {doctype}: {error_text}"
                            self.log_activity("error", error_message)
                            # Continue with other documents instead of failing completely
                except Exception as e:
                    self.log_activity("error", f"Error creating {doctype}: {str(e)}")
            
            return {"success": True, "data": created_documents}
            
        except Exception as e:
            self.log_activity("error", f"Sync error: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def fix_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fix the payload before syncing"""
        # Add any necessary transformations to the payload here
        if payload.get("doctype") == "Supplier":
            # Ensure city field exists for Supplier doctype
            if "city" not in payload:
                payload["city"] = "&nbsp;"

        if payload.get("doctype") == "Item":
            # Ensure item_group field exists for Item doctype
            if "item_group" not in payload:
                payload["item_group"] = "All Item Groups"
            if "is_stock_item" not in payload:
                payload["is_stock_item"] = 0
    
        return payload