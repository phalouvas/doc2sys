# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Doc2SysDocumentType(Document):
    def validate(self):
        """Validate document type"""
        # Ensure keywords are properly formatted
        if self.keywords:
            # Clean up keywords - remove extra spaces, convert to lowercase
            keywords = [k.strip().lower() for k in self.keywords.split(',')]
            # Remove empty entries
            keywords = [k for k in keywords if k]
            # Join back with commas
            self.keywords = ', '.join(keywords)
 