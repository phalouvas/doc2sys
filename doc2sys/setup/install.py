import subprocess
import frappe
import sys
import os

def after_install():
    """Run after app installation"""
    
    # Install dependencies
    install_dependencies()

def install_dependencies():
    # List of required Python dependencies with specific versions
    dependencies = [
        # AU Azure Document Intelligence
        "azure-ai-documentintelligence",
    ]
    
    frappe.log_error("Starting Doc2Sys dependency installation", "Doc2Sys Setup")
    
    # Install each dependency
    for package in dependencies:
        try:
            # Show installation progress
            frappe.log_error(f"Installing {package}...", "Doc2Sys Setup")
            
            # Install using bench pip 
            result = subprocess.run(
                ["bench", "pip", "install", "--quiet", package],
                check=False,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                frappe.log_error(f"✓ {package} installed successfully", "Doc2Sys Setup")
            else:
                frappe.log_error(
                    f"✗ Failed to install {package}: {result.stderr}",
                    "Doc2Sys Setup Error"
                )
                
        except Exception as e:
            frappe.log_error(
                f"✗ Error installing {package}: {str(e)}", 
                "Doc2Sys Setup Error"
            )
    
    frappe.log_error("Doc2Sys dependency installation completed", "Doc2Sys Setup")
