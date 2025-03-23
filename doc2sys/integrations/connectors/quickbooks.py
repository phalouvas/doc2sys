import frappe
import requests
from typing import Dict, Any, List
import json

from doc2sys.integrations.base import BaseIntegration
from doc2sys.integrations.registry import register_integration

@register_integration
class QuickBooksIntegration(BaseIntegration):
    """Integration with QuickBooks Online"""
    
    def authenticate(self) -> bool:
        """Authenticate with QuickBooks using OAuth"""
        try:
            access_token = self.settings.get("access_token")
            refresh_token = self.settings.get("refresh_token")
            realm_id = self.settings.get("realm_id")
            
            if not (access_token and realm_id):
                if refresh_token:
                    # Implement refresh token logic here
                    pass
                return False
                
            # Test authentication with a simple API call
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            base_url = "https://quickbooks.api.intuit.com/v3/company"
            response = requests.get(f"{base_url}/{realm_id}/companyinfo/{realm_id}", headers=headers)
            
            if response.status_code == 200:
                self.is_authenticated = True
                return True
            
            return False
        except Exception as e:
            self.log_activity("error", f"Authentication failed: {str(e)}")
            return False
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to QuickBooks"""
        if self.authenticate():
            return {"success": True, "message": "Connection to QuickBooks established"}
        return {"success": False, "message": "Failed to connect to QuickBooks"}
    
    def sync_document(self, doc2sys_item: Dict[str, Any]) -> Dict[str, Any]:
        """Sync a doc2sys_item to QuickBooks"""
        if not self.is_authenticated and not self.authenticate():
            return {"success": False, "message": "Authentication failed"}
            
        try:
            # Map fields based on the document type
            document_type = doc2sys_item.get("document_type", "").lower()
            extracted_data = doc2sys_item.get("extracted_data", {})
            
            # Create appropriate QuickBooks object based on document type
            qb_object = {}
            
            if document_type == "invoice":
                # Map invoice fields
                qb_object = {
                    "Line": [],
                    "CustomerRef": {
                        "value": extracted_data.get("customer_id", "")
                    },
                    "DocNumber": extracted_data.get("invoice_number", ""),
                    "TxnDate": extracted_data.get("invoice_date", "")
                }
                
                # Add line items
                for item in extracted_data.get("items", []):
                    line_item = {
                        "DetailType": "SalesItemLineDetail",
                        "Amount": item.get("amount", 0),
                        "SalesItemLineDetail": {
                            "ItemRef": {
                                "name": item.get("description", ""),
                            },
                            "Qty": item.get("quantity", 1),
                            "UnitPrice": item.get("unit_price", 0)
                        }
                    }
                    qb_object["Line"].append(line_item)
            
            # Get QuickBooks API credentials
            access_token = self.settings.get("access_token")
            realm_id = self.settings.get("realm_id")
            
            # Determine the endpoint based on document type
            endpoint = "invoice"
            if document_type == "bill":
                endpoint = "bill"
            elif document_type == "receipt":
                endpoint = "purchaseorder"
            
            # Send to QuickBooks
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            base_url = "https://quickbooks.api.intuit.com/v3/company"
            response = requests.post(
                f"{base_url}/{realm_id}/{endpoint}",
                headers=headers,
                json=qb_object
            )
            
            if response.status_code in (200, 201):
                result = response.json()
                self.log_activity("success", "Document synced to QuickBooks", 
                                 {"qb_id": result.get("Invoice", {}).get("Id")})
                return {"success": True, "data": result}
            else:
                self.log_activity("error", f"Failed to sync document: {response.text}")
                return {"success": False, "message": response.text}
        except Exception as e:
            self.log_activity("error", f"Sync error: {str(e)}")
            return {"success": False, "message": str(e)}
    