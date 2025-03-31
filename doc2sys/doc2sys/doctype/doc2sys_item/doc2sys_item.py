# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from doc2sys.engine.exceptions import ProcessingError
from frappe import _
from doc2sys.engine.llm_processor import LLMProcessor
from doc2sys.engine.text_extractor import TextExtractor
from doc2sys.integrations.utils import process_integrations
from frappe.handler import upload_file
from frappe.desk.form.utils import remove_attach

class Doc2SysItem(Document):
    def validate(self):
        # Check if this is a new document (being inserted)
        # We validate credits for all new documents, regardless of file attachment
        if self.is_new() and not self.flags.ignore_credit_validation:
            # Validate user credits before allowing document processing
            self.validate_user_credits()

        # Update file name and status if a file is attached
        if self.single_file:
            self.single_file_name = self.single_file.split("/")[-1]
            self.update_status()
        
    
    def validate_user_credits(self):
        """
        Check if user has sufficient credits to process a document
        Raises frappe.ValidationError if credits are insufficient
        """
        # Get the user if not already set
        user = self.user or frappe.session.user
        
        # Get user settings
        user_settings = frappe.get_all(
            'Doc2Sys User Settings',
            filters={'user': user},
            fields=['name', 'credits']
        )
        
        if not user_settings:
            frappe.throw(_("No Doc2Sys User Settings found for user {}").format(user))
        
        # Check if credits are sufficient (greater than zero)
        credits = user_settings[0].credits or 0
        
        if credits <= 0:
            frappe.throw(_(
                "Insufficient credits to process document. Current balance: {}. "
                "Please add credits to continue."
            ).format(credits))

    def after_insert(self):
        """Validate the document before saving"""
        # Set default user if not specified
        if not self.user:
            self.user = frappe.session.user
            
        if self.single_file:
            self.process_all()
      
    def _get_file_path(self):
        """Helper method to get file path from single_file URL"""
        if not self.single_file:
            return None
            
        file_doc = frappe.get_doc("File", {"file_url": self.single_file})
        if not file_doc:
            frappe.msgprint("Could not find the attached file in the system")
            return None
        
        return file_doc.get_full_path()
    
    @frappe.whitelist()
    def extract_data(self):
        if not self.single_file and not self.azure_raw_response:
            frappe.msgprint(_("No document is attached to extract data from"))
            return False
        
        try:
            file_path = self._get_file_path()
            
            # Get processor and upload file only if needed
            processor = LLMProcessor(doc2sys_item=self)
            if not processor:
                frappe.throw(_("Could not initialize document processor"))
            
            # Extract data using the appropriate document type
            # Use the document_type field from the DocType
            document_type = self.document_type or "prebuilt-invoice"  # Default to invoice if not specified
            extracted_data = processor.extract_data(file_path=file_path, document_type=document_type)
            
            if extracted_data:
                # Update status to indicate extraction is complete
                self.db_set('status', 'Processed', update_modified=True)
                
                file_doc = frappe.get_all(
                    "File", 
                    filters={
                        "attached_to_doctype": "Doc2Sys Item",
                        "attached_to_name": self.name
                    },
                    fields=["name"]
                )

                if not file_doc or len(file_doc) == 0:
                    frappe.db.commit()
                    return True
                
                frappe.form_dict["dn"] = self.name
                frappe.form_dict["dt"] = "Doc2Sys Item"
                frappe.form_dict["fid"] = file_doc[0].name
                
                # Remove the attachment using the file ID
                remove_attach()
                
                # Clear the single_file field and single_file_name
                self.db_set('single_file', '', update_modified=True)
                self.db_set('single_file_name', '', update_modified=True)
                
                frappe.db.commit()
                return True
            else:
                frappe.msgprint(_("No data could be extracted from the document"))
                return False
        
        except Exception as e:
            error_message = f"Error extracting data: {str(e)}"
            frappe.log_error(error_message, _("Document Extraction Error"))
            frappe.msgprint(_(error_message))
            return False
        
    def update_status(self):

        status = None

        if self.single_file_name:
            status = "Uploaded"

        if self.azure_raw_response:
            status = "Processed"

        if status and self.status != "Completed":
            self.db_set('status', status, update_modified=False)

    @frappe.whitelist()
    def trigger_integrations(self):
        """Trigger all configured integrations for this document"""
        try:
            # Make sure we have extracted data
            if not self.azure_raw_response:
                frappe.msgprint(_("Please extract data from the document first"))
                return False
            
            # Process integrations
            result = process_integrations(self.as_dict())
            
            # Update status based on integration results
            if result.get("success"):
                self.db_set('status', 'Completed', update_modified=True)
                frappe.db.commit()
                return result
            else:
                frappe.msgprint(_(f"Integration error: {result.get('message')}"))
                return result
                
        except Exception as e:
            error_message = f"Error processing integrations: {str(e)}"
            frappe.log_error(error_message, _("Integration Error"))
            frappe.msgprint(_(error_message))
            return {"success": False, "message": error_message}

    @frappe.whitelist()
    def process_all(self):
        """Extract data and then trigger integrations in one go"""
        if not self.single_file:
            frappe.msgprint(_("No document is attached to process"))
            return False
            
        try:
            # First extract data
            extraction_success = self.extract_data()
            if not extraction_success:
                return False
                
            # Then trigger integrations
            integration_result = self.trigger_integrations()
            return integration_result
                
        except Exception as e:
            error_message = f"Error in processing workflow: {str(e)}"
            frappe.log_error(error_message, _("Document Processing Error"))
            frappe.msgprint(_(error_message))
            return False

@frappe.whitelist()
def create_item_from_file(file_doc_name):
    """Create a Doc2Sys Item from an existing File document"""
    file_doc = frappe.get_doc("File", file_doc_name)
    if not file_doc:
        frappe.throw(_("File not found"))
    
    # Create new Doc2Sys Item with this file
    doc = frappe.new_doc("Doc2Sys Item")
    doc.single_file = file_doc.file_url
    doc.user = frappe.session.user
    doc.insert()
    
    return doc.name

@frappe.whitelist()
def upload_and_create_item():
    """
    Upload a file and create a Doc2Sys Item in one step.
    
    This endpoint accepts multipart/form-data with a file field.
    Returns the newly created Doc2Sys Item document name.
    """
    try:
        # Get the uploaded file from request
        if not frappe.request.files or 'file' not in frappe.request.files:
            return {
                "success": False,
                "message": _("No file was uploaded. Please select a file and try again.")
            }

        # Create Doc2Sys Item with this file
        doc = frappe.new_doc("Doc2Sys Item")
        doc.user = frappe.session.user
        
        try:
            # This will trigger the validate method which checks for credits
            doc.insert()
        except frappe.ValidationError as ve:
            # This will catch credit validation errors and other validation errors
            return {
                "success": False,
                "message": str(ve),
                "error_type": "validation"
            }
            
        frappe.db.commit()
        doc.reload()
        
        # Save original form values before they get consumed by upload_file
        is_private = frappe.form_dict.get('is_private')
        
        # Ensure proper type conversion for is_private
        if is_private is not None:
            # Convert to boolean if needed
            is_private = is_private.lower() == 'true' if isinstance(is_private, str) else bool(is_private)
        
        # First, upload the file using Frappe's handler
        frappe.form_dict["doctype"] = "Doc2Sys Item"
        frappe.form_dict["docname"] = doc.name
        frappe.form_dict["file_name"] = frappe.request.files['file'].filename
        frappe.form_dict["folder"] = f"Home/Doc2Sys/{doc.user}"
        
        try:
            ret = upload_file()
        except Exception as file_error:
            # If file upload fails, delete the Doc2Sys Item we just created
            frappe.delete_doc("Doc2Sys Item", doc.name, ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": False,
                "message": _("File upload failed: {}").format(str(file_error)),
                "error_type": "file_upload"
            }
            
        # Update the Doc2Sys Item with the file URL
        if ret.get("file_url"):
            doc.db_set("single_file", ret.get("file_url"))
            frappe.db.commit()
            
            # Process the document now that we have the file
            try:
                doc.process_all()
                return {
                    "success": True,
                    "message": _("Document uploaded and processed successfully"),
                    "doc2sys_item": doc.name,
                    "cost": doc.cost,
                    "extracted_data": doc.extracted_data
                }
            except Exception as process_error:
                return {
                    "success": False,
                    "message": _("Document uploaded but processing failed: {}").format(str(process_error)),
                    "doc2sys_item": doc.name,
                    "error_type": "processing"
                }
        else:
            return {
                "success": False,
                "message": _("File was uploaded but couldn't be attached to document"),
                "doc2sys_item": doc.name,
                "error_type": "attachment"
            }
            
    except frappe.ValidationError as ve:
        # This catches validation errors not handled above
        return {
            "success": False,
            "message": str(ve),
            "error_type": "validation"
        }
    except Exception as e:
        frappe.log_error(f"Error in upload_and_create_item: {str(e)}", "Doc2Sys")
        return {
            "success": False,
            "message": _("An unexpected error occurred: {}").format(str(e)),
            "error_type": "unexpected"
        }
