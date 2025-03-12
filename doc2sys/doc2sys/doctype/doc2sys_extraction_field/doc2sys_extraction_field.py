# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import re

class Doc2SysExtractionField(Document):
    def validate(self):
        """Validate extraction field"""
        # Validate regex pattern if provided
        if self.regex_pattern:
            try:
                # Test compile the regex to ensure it's valid
                re.compile(self.regex_pattern)
            except re.error:
                frappe.throw("Invalid regular expression pattern")