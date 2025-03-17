# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Doc2SysIntegrationDoctypes(Document):
	def before_save(self):
		"""Process field mapping JSON if it's provided as a string"""
		if isinstance(self.field_mapping, str):
			try:
				import json
				json.loads(self.field_mapping)  # Just validate it's valid JSON
			except Exception:
				frappe.throw("Field Mapping must be a valid JSON object")

