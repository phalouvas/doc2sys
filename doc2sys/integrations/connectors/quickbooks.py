import frappe
import requests
from typing import Dict, Any

from doc2sys.integrations.base import BaseIntegration
from doc2sys.integrations.registry import register_integration

@register_integration
class QuickBooks(BaseIntegration):
    """Integration with QuickBooks Online"""
    
    def authenticate(self) -> bool:
        """Authenticate with QuickBooks using OAuth"""
        try:
            # Get settings values
            access_token = self.settings.get("access_token")
            refresh_token = self.settings.get("refresh_token")
            realm_id = self.settings.get("realm_id")
            is_sandbox = self.settings.get("quickbooks_sandbox")
            doc_name = self.settings.get("name")
            
            # Handle environment (sandbox vs production)
            if is_sandbox:
                base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"
            else:
                base_url = "https://quickbooks.api.intuit.com/v3/company"
            
            # Try to refresh token if needed
            if not access_token and refresh_token:
                client_id = self.settings.get("client_id")
                
                # Securely get the decrypted client secret
                client_secret = ""
                if doc_name:
                    try:
                        client_secret = frappe.utils.password.get_decrypted_password(
                            "Doc2Sys User Settings", doc_name, "client_secret"
                        ) or ""
                    except Exception as e:
                        self.log_activity("error", f"Failed to get client secret: {str(e)}")
                        return False
                
                if not (client_id and client_secret):
                    self.log_activity("error", "Missing client credentials for token refresh")
                    return False
                    
                # Refresh token API endpoint
                token_endpoint = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
                refresh_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                }
                
                token_response = requests.post(
                    token_endpoint,
                    data=refresh_data,
                    auth=(client_id, client_secret)
                )
                
                if token_response.status_code != 200:
                    self.log_activity("error", f"Token refresh failed: {token_response.text}")
                    return False
                    
                token_data = token_response.json()
                
                # Update tokens in settings
                access_token = token_data.get("access_token")
                new_refresh_token = token_data.get("refresh_token")
                
                # Save the new tokens back to the settings
                frappe.db.set_value("Doc2Sys User Settings", doc_name, {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token
                })
                frappe.db.commit()
                
                self.log_activity("info", "QuickBooks tokens refreshed successfully")
            
            if not (access_token and realm_id):
                self.log_activity("error", "Missing required authentication credentials")
                return False
                
            # Test authentication with a simple API call
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            response = requests.get(f"{base_url}/{realm_id}/companyinfo/{realm_id}", headers=headers)
            
            if response.status_code == 200:
                self.is_authenticated = True
                return True
            elif response.status_code == 401:
                # Token might be expired, try refreshing
                # This handles the case where we had a valid access token but it expired during this session
                self.log_activity("info", "Access token expired, attempting refresh")
                self.is_authenticated = False
                
                # Clear the access token and retry authentication
                frappe.db.set_value("Doc2Sys User Settings", doc_name, {"access_token": ""})
                frappe.db.commit()
                
                # Recursive call to try again with refresh token
                return self.authenticate()
            else:
                self.log_activity("error", f"Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.log_activity("error", f"Authentication failed: {str(e)}")
            return False

    def get_authorization_url(self) -> Dict[str, Any]:
        """Generate QuickBooks authorization URL"""
        try:
            client_id = self.settings.get("client_id")
            doc_name = self.settings.get("name")
            
            if not client_id:
                return {"success": False, "message": "Missing client ID"}
                
            # Your callback URL - must match what's registered in QuickBooks app
            redirect_uri = frappe.utils.get_url("/quickbooks_callback")
            
            # Using the doc_name as the state parameter for security
            state = doc_name
            
            # Build authorization URL
            auth_url = "https://appcenter.intuit.com/connect/oauth2"
            auth_params = {
                "client_id": client_id,
                "response_type": "code",
                "scope": "com.intuit.quickbooks.accounting",
                "redirect_uri": redirect_uri,
                "state": state
            }
            
            auth_url_with_params = f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in auth_params.items()])}"
            
            return {
                "success": True, 
                "url": auth_url_with_params,
                "message": "Please open this URL to authorize QuickBooks access"
            }
        except Exception as e:
            self.log_activity("error", f"Failed to generate authorization URL: {str(e)}")
            return {"success": False, "message": str(e)}
    
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
    