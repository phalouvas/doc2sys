import frappe
import requests
import json
from typing import Dict, Any, List

from doc2sys.integrations.base import BaseIntegration
from doc2sys.integrations.registry import register_integration

@register_integration
class ERPNext(BaseIntegration):
    """Integration with another ERPNext instance"""
    
    def authenticate(self) -> bool:
        """Authenticate with ERPNext using API key and secret"""
        try:
            # Get credentials from settings
            api_key = self.settings.get("api_key")
            base_url = self.settings.get("base_url")
            
            # Get the name of the settings document
            doc_name = self.settings.get("name")
            
            # Get decrypted password from user settings
            api_secret = ""
            if doc_name:
                try:
                    api_secret = frappe.utils.password.get_decrypted_password(
                        "Doc2Sys User Settings", doc_name, "api_secret"
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
                
            # Transform the generic extracted data to ERPNext format
            erpnext_data = self._transform_to_erpnext_format(extracted_data, document_type)
            if not erpnext_data.get("success"):
                return erpnext_data
                
            # Get API credentials
            api_key = self.settings.get("api_key")
            doc_name = self.settings.get("name")
            
            # Get decrypted password from user settings
            api_secret = ""
            if doc_name:
                try:
                    api_secret = frappe.utils.password.get_decrypted_password(
                        "Doc2Sys User Settings", doc_name, "api_secret"
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
            items = erpnext_data.get("erpnext_docs", [])
            
            if not items:
                self.log_activity("error", "No items found in the mapped data")
                return {"success": False, "message": "No items found in the mapped data"}
            
            created_documents = {}
            
            # Define doctype priorities - lower number = higher priority
            doctype_priority = {
                "Supplier": 1,
                "Item": 2,
                "Purchase Invoice": 3,
            }
            
            # Sort items by doctype priority to ensure dependencies are created first
            # Items consistently have a nested "doc" structure in the new format
            sorted_items = sorted(items, key=lambda x: doctype_priority.get(
                x.get("doctype", ""), 999
            ))
            
            # Process each item in priority order
            for item in sorted_items:
                # New format consistently has a nested doc structure
                doc_data = item
                
                doctype = doc_data.get("doctype")
                
                if not doctype:
                    self.log_activity("error", f"Missing doctype in item")
                    continue  # Skip this item but continue with others
                
                # Special handling for Purchase Invoice with nested items and taxes
                if doctype == "Purchase Invoice":
                    # Make sure referenced items and suppliers exist in ERPNext
                    # Check if we need to map to created document names
                    if "supplier" in doc_data and "Supplier" in created_documents:
                        for supplier_name in created_documents["Supplier"]:
                            # If we have the supplier name from earlier creation, ensure it's used
                            if supplier_name.lower() in doc_data.get("supplier", "").lower():
                                doc_data["supplier"] = supplier_name
                                break
                    
                    # Ensure all line items exist - they may have simplified structure in the JSON
                    invoice_items = doc_data.get("items", [])
                    for idx, invoice_item in enumerate(invoice_items):
                        # Ensure all required fields exist for each invoice item
                        if "rate" not in invoice_item:
                            invoice_item["rate"] = 0
                        if "qty" not in invoice_item:
                            invoice_item["qty"] = 1
                        # Add doctype to each item
                        invoice_item["doctype"] = "Purchase Invoice Item"
                
                # Try to create the document directly without checking if it exists
                try:
                    create_response = requests.post(
                        f"{base_url}/api/method/frappe.client.insert",
                        json={"doc": doc_data},
                        headers=auth_headers
                    )
                    
                    if create_response.status_code in (200, 201):
                        result = create_response.json()
                        document_name = result.get("message", {}).get("name")
                        
                        if doctype not in created_documents:
                            created_documents[doctype] = []
                        
                        created_documents[doctype].append(document_name)
                    else:
                        # Check if the error is because the document already exists
                        error_text = create_response.text
                        
                        if any(phrase in error_text.lower() for phrase in ["already exists", "duplicate", "duplicateentryerror"]):
                            # For documents that already exist, try to get their identifier
                            identifier = ""
                            if doctype == "Item":
                                identifier = doc_data.get("item_code", "")
                            elif doctype == "Supplier":
                                identifier = doc_data.get("supplier_name", "")
                            
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

    def _transform_to_erpnext_format(self, extracted_data: Dict[str, Any], 
                                    document_type: str) -> Dict[str, Any]:
        """Transform generic extracted data to ERPNext-specific format"""
        try:
            if document_type in ["prebuilt-invoice"]:
                return self._transform_purchase_invoice(extracted_data)
            else:
                return {
                    "success": False,
                    "message": f"Unsupported document type for ERPNext: {document_type}"
                }
        except Exception as e:
            self.log_activity("error", f"Error transforming data for ERPNext: {str(e)}")
            return {"success": False, "message": f"Error transforming data: {str(e)}"}
        
    def _transform_purchase_invoice(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform generic invoice data to ERPNext Purchase Invoice format"""
        # Create ERPNext-specific document structure
        erpnext_docs = []
        
        # Create a Supplier doc if supplier information is available
        if extracted_data.get("supplier_name"):
            supplier_doc = {
                "doctype": "Supplier",
                "supplier_name": extracted_data.get("supplier_name"),
                "supplier_type": "Company",  # Default value
                "supplier_group": "All Supplier Groups",  # Default value
            }
            
            # Add email if available
            if extracted_data.get("supplier_email"):
                supplier_doc["email_id"] = extracted_data.get("supplier_email")
                
            # Add phone if available  
            if extracted_data.get("supplier_phone"):
                supplier_doc["mobile_no"] = extracted_data.get("supplier_phone")
                
            erpnext_docs.append(supplier_doc)
        
        # Create Item docs for each line item
        actual_items = []
        items = extracted_data.get("items", [])
        for item in items:
            # Skip special entries like totals or payment methods
            if item.get("description") and not any(keyword in item.get("description", "").lower() 
                                                  for keyword in ["total", "credit card", "payment"]):
                item_doc = {
                    "doctype": "Item",
                    "item_name": item.get("description"),
                    "item_code": item.get("item_code") or item.get("description"),
                    "item_group": "All Item Groups",  # Default value
                    "stock_uom": "Nos",  # Default value
                    "is_stock_item": 0,
                    "is_purchase_item": 1
                }
                erpnext_docs.append(item_doc)
                actual_items.append(item)
        
        # Create Purchase Invoice doc
        invoice_doc = {
            "doctype": "Purchase Invoice",
            "title": extracted_data.get("supplier_name", "Unknown"),
            "supplier": extracted_data.get("supplier_name"),
            "posting_date": extracted_data.get("invoice_date"),
            "bill_no": extracted_data.get("invoice_number"),
            "due_date": extracted_data.get("due_date"),
            "items": [],
            "taxes": []
        }
        
        # Set currency if available
        if extracted_data.get("currency"):
            invoice_doc["currency"] = extracted_data.get("currency")
        
        # Add items to the invoice (only actual product items)
        for item in actual_items:
            invoice_item = {
                "item_code": item.get("item_code") or item.get("description"),
                "item_name": item.get("description"),
                "description": item.get("description"),
                "qty": item.get("quantity", 1),
                "rate": item.get("unit_price", 0),
                "amount": item.get("amount", 0)
            }
            invoice_doc["items"].append(invoice_item)
        
        # Add tax information if available
        if extracted_data.get("tax_amount"):
            # Get the VAT account from settings or use a default value
            vat_account = self.settings.get("vat_account") or "VAT - XXX"
            
            tax_row = {
                "doctype": "Purchase Taxes and Charges",
                "charge_type": "Actual",
                "account_head": vat_account,  # Use the account from settings
                "description": "Tax",
                "tax_amount": extracted_data.get("tax_amount", 0),
                "category": "Total",
                "add_deduct_tax": "Add"
            }
            invoice_doc["taxes"].append(tax_row)
        
        # Set total amounts
        if extracted_data.get("subtotal"):
            invoice_doc["net_total"] = extracted_data.get("subtotal")
        
        if extracted_data.get("total_amount"):
            invoice_doc["grand_total"] = extracted_data.get("total_amount")
            invoice_doc["rounded_total"] = extracted_data.get("total_amount")
                
        erpnext_docs.append(invoice_doc)
        
        return {
            "success": True,
            "erpnext_docs": erpnext_docs
        }
