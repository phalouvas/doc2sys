import os
import frappe
from frappe import _
from frappe.utils import get_site_path, get_site_base_path

def get_absolute_path(path):
    """
    Convert a path to absolute path considering site directory structure.
    Checks if the path is:
    1. Already absolute
    2. Relative to site directory
    3. Relative to sites directory
    """
    if os.path.isabs(path) and os.path.exists(path):
        return path
        
    # Try relative to site directory
    site_path = os.path.join(get_site_path(), path.lstrip('/'))
    if os.path.exists(site_path):
        return site_path
        
    # Try relative to sites base directory
    base_path = os.path.join(get_site_base_path(), path.lstrip('/'))
    if os.path.exists(base_path):
        return base_path
        
    # Try relative to private directory
    private_path = os.path.join(get_site_path('private'), path.lstrip('/'))
    if os.path.exists(private_path):
        return private_path
        
    # Return the original path if all else fails
    return path

def monitor_folders():
    """
    Check monitored folder for files, process them, and delete after processing.
    This function will be called by the scheduler at the configured interval.
    """
    settings = frappe.get_single("Doc2Sys Settings")
    
    if not settings.monitoring_enabled:
        return
        
    # Get absolute path for monitor folder
    monitor_path = get_absolute_path(settings.monitor_folder)
    
    # Log the resolved path for debugging
    frappe.logger().info(f"Monitor path: {settings.monitor_folder} resolved to {monitor_path}")
    
    if not monitor_path or not os.path.isdir(monitor_path):
        frappe.log_error(_("Monitored folder does not exist or is not configured: {0} (resolved to {1})").format(
            settings.monitor_folder, monitor_path), 
            _("Doc2Sys Folder Monitor"))
        return
    
    # Get list of files in monitored folder
    files = [f for f in os.listdir(monitor_path) 
             if os.path.isfile(os.path.join(monitor_path, f))]
    
    if not files:
        return  # No files to process
    
    for file_name in files:
        file_path = os.path.join(monitor_path, file_name)

        try:
            # Upload file to Frappe file system and create Doc2SysItem
            file_url = upload_file_to_frappe(file_path, file_name)
            
            if not file_url:
                frappe.log_error(_("Failed to upload file: {0}").format(file_path),
                                _("Doc2Sys Folder Monitor"))
                continue
            
            # Create Doc2SysItem instance with the file URL
            doc2sys_item = frappe.get_doc({
                "doctype": "Doc2Sys Item",
                "title": file_name,
                "single_file": file_url,
                "file_path": file_path,
            })
            
            # Save document (which triggers file processing through validate method)
            doc2sys_item.insert()
            frappe.db.commit()

            # Delete the original file from the monitored folder
            os.remove(file_path)
            
            frappe.logger().info(_("Successfully processed and deleted file: {0}").format(file_name))
            
        except Exception as e:
            frappe.log_error(_("Error processing file {0}: {1}").format(file_name, str(e)), 
                            _("Doc2Sys Folder Monitor"))

def upload_file_to_frappe(file_path, file_name):
    """Upload file to Frappe file system and return file URL"""
    try:
        # Check if Doc2Sys folder exists, create if not
        doc2sys_folder = "Home/Doc2Sys"
        if not frappe.db.exists("File", {"is_folder": 1, "file_name": "Doc2Sys", "folder": "Home"}):
            # Create Doc2Sys folder
            folder = frappe.get_doc({
                "doctype": "File",
                "file_name": "Doc2Sys",
                "is_folder": 1,
                "folder": "Home"
            })
            folder.insert()
            frappe.logger().info("Created Doc2Sys folder for file uploads")
            
        with open(file_path, 'rb') as f:
            file_content = f.read()
            
        # Upload the file to Frappe's file system
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "folder": doc2sys_folder,
            "attached_to_doctype": "Doc2Sys Item",
            "attached_to_name": "New Doc2Sys Item",  # Temporary value
            "content": file_content
        })
        
        file_doc.insert()
        return file_doc.file_url
        
    except Exception as e:
        frappe.log_error(f"Error uploading file: {str(e)}")
        return None