import frappe
from frappe import _ 
from frappe.model.document import Document
import datetime

class Doc2SysUserSettings(Document):
    def validate(self):
        """Validate user settings"""
        if self.monitor_interval <= 0:
            frappe.throw(_("Monitor interval must be greater than 0"))
        
        self.ensure_user_folder_exists()
            
        self.update_scheduler()

    def ensure_user_folder_exists(self):
        """Create folder for the user in Doc2Sys directory if it doesn't exist"""
        user_folder_name = f"Home/Doc2Sys/{self.user}"
        if not frappe.db.exists("File", {"is_folder": 1, "file_name": self.user, "folder": user_folder_name}):
            # Create user folder
            self.create_new_folder(self.user, "Home/Doc2Sys")
            frappe.logger().info(f"Created user folder {user_folder_name} for file monitoring")

    def create_new_folder(self, file_name: str, folder: str):
        """create new folder under current parent folder"""
        file = frappe.new_doc("File")
        file.file_name = file_name
        file.is_folder = 1
        file.folder = folder
        file.insert(ignore_permissions=True, ignore_if_duplicate=True)
        return file
        
    def update_scheduler(self):
        """Update the scheduler interval for this specific user"""
        if not self.monitor_interval or not self.monitoring_enabled:
            return
            
        # Schedule logic for this specific user
        # This is just a placeholder - you'll need to implement the actual scheduler logic
        # for individual users. Possibly via a dedicated scheduled job that checks all user settings
        pass
    
@frappe.whitelist()
def process_user_folder(user_settings):
    """Process the monitored folder for a specific user"""
    settings = frappe.get_doc("Doc2Sys User Settings", user_settings)
    
    if not settings.monitoring_enabled or not settings.folder_to_monitor:
        return {
            "success": False,
            "message": "Folder monitoring is not properly configured"
        }
    
    try:
        # Import the folder monitor module
        from doc2sys.doc2sys.tasks.folder_monitor import process_folder
        
        # Process the user's specific folder
        result = process_folder(settings.folder_to_monitor, settings)
        
        return {
            "success": True,
            "message": f"Processed {result['processed']} files from {settings.folder_to_monitor}",
            "details": result
        }
    except Exception as e:
        frappe.log_error(f"Error processing folder for {settings.user}: {str(e)}", "Doc2Sys")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

@frappe.whitelist()
def test_integration_connection(user_settings, selected):
    """Test the connection for selected user integrations"""
    try:
        # Parse the selected parameter
        if isinstance(selected, str):
            import json
            selected = json.loads(selected)
            
        if not selected or not selected.get('user_integrations'):
            return {"status": "error", "message": "No integration selected"}
            
        # Get all selected integration names
        integration_names = selected['user_integrations']
        settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings)
        
        # Import the registry
        from doc2sys.integrations.registry import IntegrationRegistry
        
        # Track results for all tested integrations
        results = []
        
        # Flag to track if we need to save the settings doc
        need_to_save = False
        
        # Test each selected integration
        for integration_name in integration_names:
            # Find the integration by name
            integration = None
            for idx, integ in enumerate(settings_doc.user_integrations):
                if integ.name == integration_name:
                    integration = integ
                    break
                    
            if not integration:
                results.append({
                    "integration": integration_name,
                    "integration_type": "Unknown",
                    "status": "error", 
                    "message": "Integration not found"
                })
                continue
            
            # Get display name for the integration
            display_name = getattr(integration, "integration_name", None) or integration.integration_type
            if getattr(integration, "base_url", None):
                display_name += f" ({integration.base_url})"
                
            try:
                # Create integration instance
                integration_instance = IntegrationRegistry.create_instance(
                    integration.integration_type, 
                    settings=integration.as_dict()
                )
                
                # Test connection
                result = integration_instance.test_connection()
                
                # Set enabled status based on test result
                if result.get("success"):
                    # Enable integration if test was successful
                    if integration.enabled != 1:
                        integration.enabled = 1
                        need_to_save = True
                        result["message"] += " (Integration automatically enabled)"
                else:
                    # Disable integration if test failed
                    if integration.enabled == 1:
                        integration.enabled = 0
                        need_to_save = True
                        result["message"] += " (Integration automatically disabled)"
                
                # Add result with integration info
                results.append({
                    "integration": display_name,
                    "integration_type": integration.integration_type,
                    "status": "success" if result.get("success") else "error",
                    "message": result.get("message", "No message returned"),
                    "enabled": integration.enabled
                })
                
            except Exception as e:
                # Handle individual integration errors and disable integration
                frappe.log_error(
                    f"Connection test failed for {display_name}: {str(e)}", 
                    "Integration Error"
                )
                
                # Disable integration on exception
                was_enabled = integration.enabled
                integration.enabled = 0
                if was_enabled:
                    need_to_save = True
                
                results.append({
                    "integration": display_name,
                    "integration_type": getattr(integration, "integration_type", "Unknown"),
                    "status": "error",
                    "message": f"{str(e)} (Integration automatically disabled)",
                    "enabled": 0
                })
        
        # Save settings doc if we made any changes
        if need_to_save:
            settings_doc.save()
        
        # Determine overall status
        overall_status = "success" if all(r["status"] == "success" for r in results) else "error"
        
        # Return consolidated results
        return {
            "status": overall_status,
            "results": results,
            "message": f"Tested {len(results)} integration(s)"
        }
            
    except Exception as e:
        frappe.log_error(f"Connection test failed: {str(e)}", "Integration Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def delete_old_doc2sys_files(user_settings):
    """Delete old files from Doc2Sys Item documents based on user settings."""
    settings = frappe.get_doc("Doc2Sys User Settings", user_settings)
    
    if not settings.delete_old_files or settings.days_to_keep_files <= 0:
        return {
            "success": False,
            "message": "File deletion is not enabled or days to keep is not properly configured"
        }
    
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=settings.days_to_keep_files)
        
        # Find Doc2Sys Items older than the cutoff date that belong to this user
        old_items = frappe.get_all(
            "Doc2Sys Item",
            filters={
                "user": settings.user,
                "creation": ["<", cutoff_date]
            },
            fields=["name", "single_file"]
        )
        
        if not old_items:
            return {
                "success": True,
                "message": f"No documents older than {settings.days_to_keep_files} days found"
            }
        
        # Import the attachment removal function
        from frappe.desk.form.utils import remove_attach
        
        deleted_count = 0
        files_not_found = 0
        items_processed = 0
        
        for item in old_items:
            items_processed += 1
            
            # Skip if no file attached
            if not item.single_file:
                continue
            
            try:
                # Get the file ID based on attachment relationship
                file_doc = frappe.get_all(
                    "File", 
                    filters={
                        "attached_to_doctype": "Doc2Sys Item",
                        "attached_to_name": item.name
                    },
                    fields=["name"]
                )

                if not file_doc or len(file_doc) == 0:
                    files_not_found += 1
                    continue
                
                frappe.form_dict["dn"] = item.name
                frappe.form_dict["dt"] = "Doc2Sys Item"
                frappe.form_dict["fid"] = file_doc[0].name
                
                # Remove the attachment using the file ID
                remove_attach()
                
                # Update the document to clear the file field
                doc = frappe.get_doc("Doc2Sys Item", item.name)
                doc.single_file = ""
                doc.save()
                
                deleted_count += 1
                
            except Exception as e:
                frappe.log_error(f"Error deleting file from {item.name}: {str(e)}", "Doc2Sys File Cleanup")
                files_not_found += 1
        
        return {
            "success": True,
            "message": f"Processed {items_processed} documents, deleted {deleted_count} files, {files_not_found} files not found or had errors",
            "details": {
                "items_processed": items_processed,
                "files_deleted": deleted_count,
                "files_not_found": files_not_found
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Error during Doc2Sys file cleanup: {str(e)}", "Doc2Sys File Cleanup")
        return {
            "success": False,
            "message": f"Error during file cleanup: {str(e)}"
        }
