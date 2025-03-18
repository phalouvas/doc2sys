import subprocess
import frappe
import sys
import os

def after_install():
    """Run after app installation"""
    # List of required Python dependencies with specific versions
    dependencies = [
        # Core dependencies (install first)
        "numpy>=1.21.0",           # Numeric processing - base requirement
        "pillow>=9.0.0",           # Image processing
        "opencv-python-headless",  # OpenCV for image preprocessing (headless version for servers)
        
        # Document processing
        "python-docx",             # For processing Microsoft Word documents
        "PyPDF2>=2.0.0",           # For PDF text extraction
        "pandas",                  # For data processing
        
        # OCR dependencies
        "pytesseract",             # Python wrapper for Tesseract OCR
        "pdf2image",               # For PDF to image conversion for OCR
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
    
    # Display message about system dependencies
    frappe.log_error(
        "IMPORTANT: To use OCR features, you must install Tesseract OCR on your system.",
        "Doc2Sys Setup"
    )
    frappe.log_error(
        "For Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-ell",
        "Doc2Sys Setup"
    )
    
    # Verify key installations
    try:
        verify_packages = ["pytesseract", "PyPDF2", "docx", "cv2", "pdf2image"]
        for pkg in verify_packages:
            try:
                module = __import__(pkg)
                frappe.log_error(f"✓ {pkg} verified - version: {getattr(module, '__version__', 'unknown')}", "Doc2Sys Setup")
            except ImportError:
                frappe.log_error(f"✗ {pkg} import failed after installation", "Doc2Sys Setup Error")
    except Exception as e:
        frappe.log_error(f"Failed to verify package installations: {str(e)}", "Doc2Sys Setup Error")
        
    # Check if Tesseract is installed on the system
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        frappe.log_error(f"✓ Tesseract OCR found - version: {version}", "Doc2Sys Setup")
        
        # Get available languages
        languages = pytesseract.get_languages()
        frappe.log_error(f"✓ Tesseract languages available: {', '.join(languages)}", "Doc2Sys Setup")
    except Exception as e:
        frappe.log_error(f"✗ Unable to detect Tesseract OCR: {str(e)}", "Doc2Sys Setup Error")
    
    # Initialize default settings
    try:
        # Create default OCR language settings if needed
        if not frappe.db.exists("DocType", "Doc2Sys OCR Language"):
            frappe.log_error("Setting up default OCR languages", "Doc2Sys Setup")
            settings = frappe.get_doc("Doc2Sys Settings")
            settings.add_common_languages()
    except Exception as e:
        frappe.log_error(f"Failed to setup initial settings: {str(e)}", "Doc2Sys Setup Error")
        
    frappe.log_error("Doc2Sys dependency installation completed", "Doc2Sys Setup")