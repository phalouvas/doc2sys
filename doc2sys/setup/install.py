import subprocess
import frappe

def after_install():
    """Run after app installation"""
    # List of required Python dependencies
    dependencies = [
        "python-docx",  # For processing Microsoft Word documents
        "pdf2image",    # For converting PDF pages to images for OCR
    ]
    
    # Install each dependency
    for package in dependencies:
        try:
            # Install using bench pip
            subprocess.run(["bench", "pip", "install", package], check=True)
            frappe.log_error(f"{package} installed successfully", "Doc2Sys Setup")
        except Exception as e:
            frappe.log_error(f"Failed to install {package}: {str(e)}", "Doc2Sys Setup Error")
    
    # Log completion message
    frappe.log_error("Doc2Sys dependency installation completed", "Doc2Sys Setup")