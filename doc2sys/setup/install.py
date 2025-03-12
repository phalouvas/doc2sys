import subprocess
import frappe
import sys
import os

def after_install():
    """Run after app installation"""
    # List of required Python dependencies in proper order
    dependencies = [
        "numpy",             # Base scientific computing - must be installed first
        "python-docx",       # For processing Microsoft Word documents
        "pdf2image",         # For converting PDF pages to images for OCR
        "scikit-learn>=1.0", # For ML-based document classification
        "spacy>=3.5.0",      # NLP library for entity extraction and classification
    ]
    
    # Install each dependency
    for package in dependencies:
        try:
            # Install using bench pip
            subprocess.run(["bench", "pip", "install", package], check=True)
            frappe.log_error(f"{package} installed successfully", "Doc2Sys Setup")
        except Exception as e:
            frappe.log_error(f"Failed to install {package}: {str(e)}", "Doc2Sys Setup Error")
    
    # Download spaCy models
    try:
        # Use Python's subprocess to run the spaCy download command
        frappe.log_error("Attempting to download spaCy model...", "Doc2Sys Setup")
        
        # Get the path to the Python executable that bench is using
        python_cmd = sys.executable
        
        # Use that Python to run spacy download
        subprocess.run([python_cmd, "-m", "spacy", "download", "en_core_web_md"], 
                      check=True, 
                      env=os.environ.copy())
        
        frappe.log_error("spaCy English model downloaded successfully", "Doc2Sys Setup")
    except Exception as e:
        frappe.log_error(f"Failed to download spaCy model: {str(e)}", "Doc2Sys Setup Error")
        try:
            # Try downloading a smaller model as fallback
            frappe.log_error("Attempting to download smaller spaCy model...", "Doc2Sys Setup")
            subprocess.run([python_cmd, "-m", "spacy", "download", "en_core_web_sm"], 
                          check=True, 
                          env=os.environ.copy())
            frappe.log_error("spaCy small English model downloaded successfully", "Doc2Sys Setup")
        except Exception as e:
            frappe.log_error(f"Failed to download spaCy small model: {str(e)}", "Doc2Sys Setup Error")