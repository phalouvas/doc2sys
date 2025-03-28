import json
import requests
import frappe
from typing import Dict, Any, Optional, List

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
        # First authenticate - this ensures we have valid tokens
        if not self.authenticate():
            return {"success": False, "message": "Authentication failed"}
        
        try:
            # Get fresh token after authentication
            access_token = self.settings.get("access_token")
            realm_id = self.settings.get("realm_id")
            
            # Debug log to check token
            self.log_activity("debug", "Using access token and realm ID", {
                "token_length": len(access_token) if access_token else 0,
                "realm_id": realm_id
            })
            
            # Verify we have the necessary credentials
            if not access_token or not realm_id:
                return {"success": False, "message": "Missing authentication credentials"}
            
            # Track the current document
            self.current_document = doc2sys_item.get("name")
            
            # Get document type
            document_type = doc2sys_item.get("document_type", "").lower()
            
            # Get extracted data
            try:
                extracted_data = doc2sys_item.get("extracted_data", "{}")
                if isinstance(extracted_data, str):
                    extracted_data = json.loads(extracted_data)
            except json.JSONDecodeError:
                self.log_activity("error", "Invalid JSON in extracted_data")
                return {"success": False, "message": "Invalid JSON in extracted_data"}
                
            # Transform the generic extracted data to QuickBooks format
            qb_data = self._transform_to_quickbooks_format(extracted_data, document_type)
            if not qb_data.get("success"):
                return qb_data
                
            # Get API credentials
            is_sandbox = self.settings.get("quickbooks_sandbox")
            
            # Determine base URL based on environment
            if is_sandbox:
                base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"
            else:
                base_url = "https://quickbooks.api.intuit.com/v3/company"
            
            # Prepare the request
            qb_object = qb_data.get("qb_object", {})
            endpoint = qb_data.get("endpoint", "")
            
            if not endpoint:
                return {"success": False, "message": f"Unsupported document type: {document_type}"}
                
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            self.log_activity("info", f"Sending {document_type} to QuickBooks", {
                "endpoint": endpoint,
                "object_size": len(str(qb_object))
            })
            
            # Make the API call
            response = requests.post(
                f"{base_url}/{realm_id}/{endpoint}",
                headers=headers,
                json=qb_object
            )
            
            # If unauthorized, try refreshing token and retrying once
            if response.status_code == 401:
                self.log_activity("warning", "Token expired during request, refreshing")
                
                # Explicitly clear token to force refresh
                frappe.db.set_value("Doc2Sys User Settings", self.settings.get("name"), {"access_token": ""})
                frappe.db.commit()
                
                # Authenticate again to get fresh token
                if not self.authenticate():
                    return {"success": False, "message": "Failed to refresh authentication"}
                
                # Get fresh token after re-authentication
                fresh_token = self.settings.get("access_token")
                headers["Authorization"] = f"Bearer {fresh_token}"
                
                # Retry request with new token
                response = requests.post(
                    f"{base_url}/{realm_id}/{endpoint}",
                    headers=headers,
                    json=qb_object
                )
            
            if response.status_code in (200, 201):
                result = response.json()
                
                # Extract the response ID based on document type
                qb_id = None
                if document_type == "invoice":
                    qb_id = result.get("Invoice", {}).get("Id")
                elif document_type in ["bill", "purchase invoice"]:
                    qb_id = result.get("Bill", {}).get("Id")
                
                self.log_activity("success", f"{document_type.capitalize()} synced to QuickBooks", {
                    "qb_id": qb_id,
                    "response_size": len(str(result))
                })
                
                return {
                    "success": True, 
                    "data": result, 
                    "message": f"{document_type.capitalize()} successfully created in QuickBooks"
                }
            else:
                error_message = f"Failed to sync {document_type}: {response.status_code} - {response.text}"
                self.log_activity("error", error_message)
                return {"success": False, "message": error_message}
                
        except Exception as e:
            self.log_activity("error", f"Sync error: {str(e)}")
            return {"success": False, "message": str(e)}

    def _transform_to_quickbooks_format(self, extracted_data: Dict[str, Any], 
                                        document_type: str) -> Dict[str, Any]:
        """Transform generic extracted data to QuickBooks API format"""
        try:
            # Smart detection of document type based on available fields
            has_supplier = bool(extracted_data.get("supplier_name"))
            has_customer = bool(extracted_data.get("customer_name") or extracted_data.get("customer_id"))
            
            # If it has supplier info but no customer info, it's likely a bill
            if has_supplier and not has_customer:
                self.log_activity("info", "Document detected as a bill based on content", {
                    "supplier": extracted_data.get("supplier_name")
                })
                return self._transform_bill(extracted_data)
                
            # If it has customer info but no supplier info, it's likely an invoice
            elif has_customer and not has_supplier:
                self.log_activity("info", "Document detected as an invoice based on content", {
                    "customer": extracted_data.get("customer_name")
                })
                return self._transform_invoice(extracted_data)
                
            # Honor explicit document_type if available
            elif document_type == "invoice":
                return self._transform_invoice(extracted_data)
            elif document_type in ["bill", "purchase invoice"]:
                return self._transform_bill(extracted_data)
            elif document_type == "receipt":
                return self._transform_receipt_to_bill(extracted_data)
            else:
                # Default to bill if document has supplier info
                if has_supplier:
                    return self._transform_bill(extracted_data)
                # Default to invoice if no supplier but we need to add a default customer
                else:
                    return self._transform_invoice_with_default_customer(extracted_data)
        except Exception as e:
            self.log_activity("error", f"Error transforming data for QuickBooks: {str(e)}")
            return {"success": False, "message": f"Error transforming data: {str(e)}"}

    def _transform_invoice(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform generic invoice data to QuickBooks Invoice format"""
        # Initialize QuickBooks invoice object
        qb_invoice = {
            "Line": [],
            "CustomerRef": {
                "value": extracted_data.get("customer_id", "1")  # Default to first customer if not found
            },
            "DocNumber": extracted_data.get("invoice_number", ""),
            "TxnDate": extracted_data.get("invoice_date", "")
        }
        
        # Add customer name if available
        if extracted_data.get("customer_name"):
            qb_invoice["CustomerRef"]["name"] = extracted_data.get("customer_name")
            
        # Add due date if available
        if extracted_data.get("due_date"):
            qb_invoice["DueDate"] = extracted_data.get("due_date")
            
        # Add line items
        items = extracted_data.get("items", [])
        for item in items:
            line_item = {
                "DetailType": "SalesItemLineDetail",
                "Amount": item.get("amount", 0),
                "Description": item.get("description", ""),
                "SalesItemLineDetail": {
                    "ItemRef": {
                        "name": item.get("description", ""),
                    },
                    "Qty": item.get("quantity", 1),
                    "UnitPrice": item.get("unit_price", 0)
                }
            }
            
            # Add item code if available
            if item.get("item_code"):
                line_item["SalesItemLineDetail"]["ItemRef"]["value"] = item.get("item_code")
                
            qb_invoice["Line"].append(line_item)
            
        return {
            "success": True,
            "qb_object": qb_invoice,
            "endpoint": "invoice"
        }
            
    def _transform_bill(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform generic invoice/bill data to QuickBooks Bill format"""
        # Initialize QuickBooks bill object
        qb_bill = {
            "Line": [],
            "VendorRef": {
                "name": extracted_data.get("supplier_name", "Unknown Vendor"),
                "value": extracted_data.get("supplier_id", "1")  # Default to ID 1 if missing
            },
            "DocNumber": extracted_data.get("invoice_number", ""),
            "TxnDate": extracted_data.get("invoice_date", "")
        }
        
        # Override with supplier ID if available
        if extracted_data.get("supplier_id"):
            qb_bill["VendorRef"]["value"] = extracted_data.get("supplier_id")
            
        # Add due date if available
        if extracted_data.get("due_date"):
            qb_bill["DueDate"] = extracted_data.get("due_date")
            
        # Add total amount if available
        if extracted_data.get("total_amount"):
            qb_bill["TotalAmt"] = extracted_data.get("total_amount")
            
        # Get tax code from settings or use default
        tax_code = self.settings.get("qb_tax_code") or "NON"
        
        # Get expense account from settings or use default
        expense_account_id = self.settings.get("qb_expense_account") or "7"  # Default expense account ID
        
        # Add line items
        items = extracted_data.get("items", [])
        for item in items:
            line_item = {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": item.get("amount", 0),
                "Description": item.get("description", ""),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {
                        "name": "Expenses",
                        "value": expense_account_id  # Using account ID from settings
                    },
                    "BillableStatus": "NotBillable",
                    "TaxCodeRef": {
                        "value": tax_code  # Use tax code from settings
                    }
                }
            }
            
            # Add tax information if available
            if item.get("tax_amount"):
                line_item["AccountBasedExpenseLineDetail"]["TaxAmount"] = item.get("tax_amount")
                
            qb_bill["Line"].append(line_item)
            
        return {
            "success": True,
            "qb_object": qb_bill,
            "endpoint": "bill"
        }

    def _transform_receipt_to_bill(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform receipt data to QuickBooks Bill format"""
        # Initialize QuickBooks bill object from receipt data
        merchant_name = extracted_data.get("merchant_name", "Unknown Vendor")
        qb_bill = {
            "Line": [],
            "VendorRef": {
                "name": merchant_name,
                "value": "1"  # Default vendor ID if not found
            },
            "DocNumber": extracted_data.get("receipt_number", ""),
            "TxnDate": extracted_data.get("transaction_date", "")
        }
        
        # Add total amount if available
        if extracted_data.get("total_amount"):
            qb_bill["TotalAmt"] = extracted_data.get("total_amount")
            
        # Get tax code from settings or use default
        tax_code = self.settings.get("qb_tax_code") or "NON"
        
        # Get expense account from settings or use default
        expense_account_id = self.settings.get("qb_expense_account") or "7"  # Default expense account ID
        
        # Add line items
        items = extracted_data.get("items", [])
        for item in items:
            line_item = {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": item.get("total_price", 0) or item.get("price", 0),
                "Description": item.get("description", ""),
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {
                        "name": "Expenses",
                        "value": expense_account_id  # Using account ID from settings
                    },
                    "BillableStatus": "NotBillable",
                    "TaxCodeRef": {
                        "value": tax_code  # Use tax code from settings
                    }
                }
            }
            
            qb_bill["Line"].append(line_item)
            
        return {
            "success": True,
            "qb_object": qb_bill,
            "endpoint": "bill"
        }
