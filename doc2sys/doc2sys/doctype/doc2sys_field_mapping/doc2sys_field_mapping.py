# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Doc2SysFieldMapping(Document):
    def validate(self):
        """Validate field mapping"""
        self.validate_target_field()
    
    def validate_target_field(self):
        """Validate that target field exists in the target doctype"""
        if not self.target_doctype or not self.target_field:
            return
            
        try:
            # Check if the target field exists in the target doctype
            meta = frappe.get_meta(self.target_doctype)
            if not meta.has_field(self.target_field):
                frappe.msgprint(
                    f"Field '{self.target_field}' does not exist in DocType '{self.target_doctype}'",
                    title="Warning: Invalid Field Mapping",
                    indicator="orange"
                )
        except Exception as e:
            frappe.log_error(f"Error validating field mapping: {str(e)}")
    
    @staticmethod
    def get_field_mappings(target_doctype=None):
        """
        Get all field mappings for a specific target doctype
        
        Args:
            target_doctype: Optional target doctype name to filter by
            
        Returns:
            dict: Mapping of source_field to target_field
        """
        filters = {"enabled": 1}
        if target_doctype:
            filters["target_doctype"] = target_doctype
            
        mappings = frappe.get_all(
            "Doc2Sys Field Mapping",
            filters=filters,
            fields=["source_field", "target_field", "target_doctype"]
        )
        
        # Group mappings by target_doctype
        result = {}
        for mapping in mappings:
            doctype = mapping.target_doctype
            if doctype not in result:
                result[doctype] = {}
                
            result[doctype][mapping.source_field] = mapping.target_field
            
        return result if not target_doctype else result.get(target_doctype, {})