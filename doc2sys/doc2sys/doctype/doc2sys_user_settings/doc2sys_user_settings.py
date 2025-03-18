import frappe
from frappe import _ 
from frappe.model.document import Document

class Doc2SysUserSettings(Document):
    def validate(self):
        """Validate user settings"""
        if self.monitor_interval <= 0:
            frappe.throw(_("Monitor interval must be greater than 0"))
        
        # Ensure at least one OCR language is enabled if OCR is enabled
        if self.ocr_enabled and not any(lang.enabled for lang in self.ocr_languages):
            frappe.throw(_("At least one OCR language must be enabled if OCR is activated."))

    def get_enabled_languages(self):
        """Return a list of enabled OCR languages"""
        return [lang.language_code for lang in self.ocr_languages if lang.enabled]

    def get_llm_provider_options(self):
        """Return available options for LLM provider"""
        return ["Open WebUI"]  # Add more options as needed

    @frappe.whitelist()
    def update_settings(self, settings):
        """Update user-specific settings"""
        for key, value in settings.items():
            setattr(self, key, value)
        self.save()