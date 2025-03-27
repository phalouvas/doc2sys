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
def test_integration(user_settings):
    """Test the connection for the user integration settings"""
    try:
        settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings)
        
        # Import the registry
        from doc2sys.integrations.registry import IntegrationRegistry
        
        # Validate required integration fields
        if not getattr(settings_doc, "integration_type", None):
            return {"status": "error", "message": "Integration type not configured"}
            
        # Get display name for the integration
        display_name = settings_doc.integration_type
        if getattr(settings_doc, "base_url", None):
            display_name += f" ({settings_doc.base_url})"
            
        need_to_save = False
        
        try:
            # Create integration instance using fields directly from settings document
            integration_instance = IntegrationRegistry.create_instance(
                settings_doc.integration_type, 
                settings=settings_doc.as_dict()
            )
            
            # Test connection
            result = integration_instance.test_connection()
            
            # Set enabled status based on test result
            if result.get("success"):
                # Enable integration if test was successful
                if getattr(settings_doc, "integration_enabled", 0) != 1:
                    settings_doc.integration_enabled = 1
                    need_to_save = True
                    result["message"] += " (Integration automatically enabled)"
            else:
                # Disable integration if test failed
                if getattr(settings_doc, "integration_enabled", 0) == 1:
                    settings_doc.integration_enabled = 0
                    need_to_save = True
                    result["message"] += " (Integration automatically disabled)"
            
            # Save settings doc if we made any changes
            if need_to_save:
                settings_doc.save()
            
            return {
                "status": "success" if result.get("success") else "error",
                "integration": display_name,
                "integration_type": settings_doc.integration_type,
                "message": result.get("message", "No message returned"),
                "enabled": getattr(settings_doc, "integration_enabled", 0)
            }
                
        except Exception as e:
            # Handle integration errors and disable integration
            frappe.log_error(
                f"Connection test failed for {display_name}: {str(e)}", 
                "Integration Error"
            )
            
            # Disable integration on exception
            was_enabled = getattr(settings_doc, "integration_enabled", 0)
            settings_doc.integration_enabled = 0
            if was_enabled:
                settings_doc.save()
            
            return {
                "status": "error",
                "integration": display_name,
                "integration_type": settings_doc.integration_type,
                "message": f"{str(e)} (Integration automatically disabled)",
                "enabled": 0
            }
            
    except Exception as e:
        frappe.log_error(f"Connection test failed: {str(e)}", "Integration Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def test_integration_user(user):
    """Test the connection for the user integration settings"""
    try:
        # Get the user settings
        settings_doc = frappe.get_all(
            "Doc2Sys User Settings",
            filters={"user": user},
            fields=["name"]
        )
        
        if not settings_doc or len(settings_doc) == 0:
            return {"status": "error", "message": "User settings not found"}
        
        # Test the integration for the user
        return test_integration(settings_doc[0].name)
        
    except Exception as e:
        frappe.log_error(f"Connection test failed for {user}: {str(e)}", "Integration Error")
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

@frappe.whitelist()
def get_user_credits(user=None):
    """Get the available credits for a user.
    
    Args:
        user (str, optional): The user to get credits for. 
                             If not provided, uses the current user.
    
    Returns:
        dict: A dictionary containing the credits and status information
    """
    try:
        # If no user specified, use current user
        if not user:
            user = frappe.session.user
            
        # Get the user settings
        settings_doc = frappe.get_all(
            "Doc2Sys User Settings",
            filters={"user": user},
            fields=["name", "credits"]
        )
        
        if not settings_doc or len(settings_doc) == 0:
            return {
                "success": False,
                "credits": 0,
                "message": "User settings not found"
            }
        
        # Return the credits
        return {
            "success": True,
            "credits": settings_doc[0].credits or 0,
            "settings_id": settings_doc[0].name
        }
        
    except Exception as e:
        frappe.log_error(f"Error retrieving credits for {user}: {str(e)}", "Doc2Sys")
        return {
            "success": False,
            "credits": 0,
            "message": f"Error: {str(e)}"
        }

@frappe.whitelist()
def get_quickbooks_auth_url(user_settings):
    """Generate QuickBooks authorization URL"""
    try:
        # Get user settings
        settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings)
        
        # Validate required fields
        if not settings_doc.integration_type == "QuickBooks":
            return {"success": False, "message": "Not a QuickBooks integration"}
            
        if not (settings_doc.client_id and settings_doc.client_secret):
            return {"success": False, "message": "Missing QuickBooks credentials (Client ID and Secret required)"}
            
        # Import registry and create integration instance
        from doc2sys.integrations.registry import IntegrationRegistry
        
        integration_instance = IntegrationRegistry.create_instance(
            "QuickBooks", 
            settings=settings_doc.as_dict()
        )
        
        # Get authorization URL from integration instance
        auth_result = integration_instance.get_authorization_url()
        
        return auth_result
            
    except Exception as e:
        frappe.log_error(f"Error generating QuickBooks authorization URL: {str(e)}", "Integration Error")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def get_quickbooks_auth_url_for_user(user=None):
    """Generate QuickBooks authorization URL for the current user"""
    try:
        if not user:
            user = frappe.session.user
            
        # Get user settings doc for this user
        settings_name = frappe.db.get_value("Doc2Sys User Settings", {"user": user})
        
        if not settings_name:
            return {"success": False, "message": "User settings not found"}
            
        # Call the existing method with the retrieved settings name
        return get_quickbooks_auth_url(settings_name)
            
    except Exception as e:
        frappe.log_error(f"Error generating QuickBooks authorization URL for user: {str(e)}", "Integration Error")
        return {"success": False, "message": str(e)}
