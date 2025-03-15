# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Doc2SysSettings(Document):
    def validate(self):
        """Validate settings"""
        if self.max_file_size_mb <= 0:
            frappe.throw("Maximum file size must be greater than 0")
        self.update_scheduler()
            
    def get_supported_file_extensions(self):
        """Return list of supported file extensions"""
        return [ft.file_extension.lower().strip() for ft in self.supported_file_types if ft.file_extension]
    
    def get_max_file_size_bytes(self):
        """Return max file size in bytes"""
        return self.max_file_size_mb * 1024 * 1024

    def update_scheduler(self):
        """Update the scheduler interval based on settings"""
        if not self.monitor_interval or not self.monitoring_enabled:
            return
            
        # Get the current job
        job = frappe.get_all(
            "Scheduled Job Type",
            filters={"method": "doc2sys.doc2sys.tasks.folder_monitor.monitor_folders"},
            fields=["name", "cron_format"]
        )
        
        if not job:
            return
            
        # Create the new cron format based on settings
        new_cron = f"*/{self.monitor_interval} * * * *"
        
        # Update the job if needed
        if job[0].cron_format != new_cron:
            frappe.db.set_value("Scheduled Job Type", job[0].name, "cron_format", new_cron)
            frappe.db.commit()

@frappe.whitelist()
def run_folder_monitor():
    """Manually run the folder monitor process"""
    from doc2sys.doc2sys.tasks.folder_monitor import monitor_folders
    monitor_folders()
    return {
        "success": True,
        "message": "Folder monitoring process completed"
    }
