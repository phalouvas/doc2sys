import os
import frappe
from frappe import _
from frappe.utils import get_site_path, get_site_base_path
from doc2sys.engine.config import EngineConfig

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
    Check monitored folders for all users with folder monitoring enabled.
    This function will be called by the scheduler at the configured interval.
    """
    # Get all users with folder monitoring enabled
    user_settings_list = frappe.get_all(
        "Doc2Sys User Settings",
        filters={
            "monitoring_enabled": 1
        },
        fields=["name", "user", "folder_to_monitor"]
    )
    
    if not user_settings_list:
        frappe.logger().debug("No users with folder monitoring enabled")
        return
    
    results = {
        "processed": 0,
        "errors": 0,
        "users": []
    }
    
    # Process folder for each user with monitoring enabled
    for user_setting in user_settings_list:
        user = user_setting.user
        folder = user_setting.folder_to_monitor
        
        if not folder:
            frappe.logger().debug(f"User {user} has monitoring enabled but no folder configured")
            continue
        
        try:
            # Get full user settings document
            user_doc = frappe.get_doc("Doc2Sys User Settings", user_setting.name)
            
            # Process this user's folder
            frappe.logger().info(f"Processing monitored folder for user {user}")
            result = process_folder(folder, user_doc)
            
            # Add results to overall summary
            results["processed"] += result.get("processed", 0)
            results["errors"] += result.get("errors", 0)
            results["users"].append({
                "user": user,
                "processed": result.get("processed", 0),
                "errors": result.get("errors", 0)
            })
            
        except Exception as e:
            frappe.log_error(
                f"Error monitoring folder for user {user}: {str(e)}",
                "Doc2Sys Folder Monitor"
            )
            results["errors"] += 1
    
    return results

def process_folder(folder_path, user_settings):
    """
    Process a specific folder for a specific user.
    
    Args:
        folder_path (str): Path to the folder to monitor
        user_settings (Doc2SysUserSettings): User settings document
    
    Returns:
        dict: Results of the processing
    """
    user = user_settings.user
    
    # Get absolute path for monitor folder
    monitor_path = get_absolute_path(folder_path)
    
    # Log the resolved path for debugging
    frappe.logger().info(f"Monitor path for user {user}: {folder_path} resolved to {monitor_path}")
    
    results = {
        "processed": 0,
        "errors": 0,
        "files": []
    }
    
    if not monitor_path or not os.path.isdir(monitor_path):
        frappe.log_error(
            f"Monitored folder does not exist or is not configured for user {user}: {folder_path} (resolved to {monitor_path})",
            "Doc2Sys Folder Monitor"
        )
        return results
    
    # Get global settings for max file size and supported types
    global_settings = frappe.get_single("Doc2Sys Settings")
    max_file_size = global_settings.get_max_file_size_bytes()
    supported_extensions = global_settings.get_supported_file_extensions()
    
    # Get list of files in monitored folder
    try:
        files = [f for f in os.listdir(monitor_path) if os.path.isfile(os.path.join(monitor_path, f))]
    except Exception as e:
        frappe.log_error(
            f"Error reading directory {monitor_path} for user {user}: {str(e)}",
            "Doc2Sys Folder Monitor"
        )
        results["errors"] += 1
        return results
    
    if not files:
        frappe.logger().debug(f"No files found in {monitor_path} for user {user}")
        return results  # No files to process
    
    for file_name in files:
        file_path = os.path.join(monitor_path, file_name)
        file_result = {
            "file": file_name,
            "success": False,
            "error": None
        }

        try:
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > max_file_size:
                error_msg = f"File exceeds maximum size limit ({file_size} > {max_file_size} bytes)"
                frappe.logger().warning(f"{error_msg}: {file_path}")
                file_result["error"] = error_msg
                results["errors"] += 1
                results["files"].append(file_result)
                continue
            
            # Check file extension
            _, ext = os.path.splitext(file_name)
            ext = ext.lstrip('.').lower()
            if ext not in supported_extensions:
                error_msg = f"Unsupported file type: {ext}"
                frappe.logger().warning(f"{error_msg}: {file_path}")
                file_result["error"] = error_msg
                results["errors"] += 1
                results["files"].append(file_result)
                continue
            
            # Use a similar approach
            with open(file_path, 'rb') as f:
                file_content = f.read()

            file_doc = frappe.get_doc(
                {
                    "doctype": "File",
                    "attached_to_doctype": None,
                    "attached_to_name": None,
                    "attached_to_field": None,
                    "folder": f"Home/Doc2Sys/{user}",
                    "file_name": file_name,
                    "file_url": None,
                    "is_private": 1,
                    "content": file_content,
                }
            ).save(ignore_permissions=False)
            
            # Create Doc2Sys Item in a more standard way
            doc2sys_item = frappe.new_doc("Doc2Sys Item")
            doc2sys_item.single_file = file_doc.file_url
            doc2sys_item.owner = user
            doc2sys_item.user = user
            doc2sys_item.insert()
            frappe.db.commit()

            file_doc.reload()
            file_doc.attached_to_doctype = "Doc2Sys Item"
            file_doc.attached_to_name = doc2sys_item.name
            file_doc.attached_to_field = "single_file"
            file_doc.save(ignore_permissions=False)
            frappe.db.commit()

            # Delete the original file from the monitored folder
            os.remove(file_path)
            
            # Update results
            frappe.logger().info(f"Successfully processed and deleted file: {file_name} for user {user}")
            results["processed"] += 1
            file_result["success"] = True
            results["files"].append(file_result)
            
        except Exception as e:
            error_msg = str(e)
            frappe.log_error(
                f"Error processing file {file_name} for user {user}: {error_msg}", 
                "Doc2Sys Folder Monitor"
            )
            file_result["error"] = error_msg
            results["errors"] += 1
            results["files"].append(file_result)

    return results
