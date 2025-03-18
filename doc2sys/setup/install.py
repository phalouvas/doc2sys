import subprocess
import frappe
import sys
import os

def after_install():
    """Run after app installation"""
    # List of required Python dependencies with specific versions
    dependencies = [
        # Core dependencies 
        "numpy",                # Numeric processing
        "pillow",               # Image processing (more stable than pdf2image)
        "opencv-python",        # OpenCV for image preprocessing (standard version)
        
        # Document processing
        "python-docx",          # For processing Microsoft Word documents
        "PyPDF2",         # For PDF text extraction
        "pandas",               # For data processing
        
        # OCR - install last after other dependencies
        "easyocr",              # For OCR (without version constraint)
    ]
    
    # Install each dependency
    for package in dependencies:
        try:
            # Install using bench pip without forcing reinstall
            subprocess.run(["bench", "pip", "install", package], check=True)
            frappe.log_error(f"{package} installed successfully", "Doc2Sys Setup")
        except Exception as e:
            frappe.log_error(f"Failed to install {package}", "Doc2Sys Setup Error")