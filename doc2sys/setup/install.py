import subprocess
import frappe

def after_install():
    """Run after app installation"""
    try:
        # Install python-docx
        subprocess.run(["bench", "pip", "install", "python-docx"], check=True)
        frappe.log_error("python-docx installed successfully", "Doc2Sys Setup")
    except Exception as e:
        frappe.log_error(f"Failed to install python-docx: {str(e)}", "Doc2Sys Setup Error")