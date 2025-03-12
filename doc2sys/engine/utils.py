"""
Utility functions for the document processing engine.
"""

import os
import logging
import frappe
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('doc2sys.engine')

def get_file_extension(file_path):
    """Get the extension of a file"""
    import os
    _, extension = os.path.splitext(file_path)
    return extension.lower()[1:] if extension else ""

def is_supported_file_type(file_path, supported_types=None):
    """
    Check if the file type is supported by the engine
    
    Args:
        file_path: Path to the file
        supported_types: List of supported file extensions
        
    Returns:
        bool: True if supported, False otherwise
    """
    if supported_types is None:
        supported_types = ['pdf', 'docx', 'txt', 'jpg', 'png']
        
    ext = get_file_extension(file_path)
    return ext in supported_types

def check_spacy_model_availability():
    """Check which spaCy models are available and log the results"""
    models_to_check = ["en_core_web_md", "en_core_web_sm", "en-core-web-md"]
    available_models = []
    
    # Try to import spacy
    try:
        import spacy
        import spacy.util
        
        # Check each model using spacy's utility function
        for model in models_to_check:
            if spacy.util.is_package(model):
                available_models.append(model)
                
        # If no models found using spacy.util, try direct import
        if not available_models:
            for model in models_to_check:
                if importlib.util.find_spec(model) is not None:
                    available_models.append(model)
    
    except ImportError:
        frappe.log_error("spaCy not installed", "Doc2Sys spaCy Check")
        return False, []
        
    # Log results
    if available_models:
        frappe.log_error(f"Available spaCy models: {', '.join(available_models)}", "Doc2Sys spaCy Check")
        return True, available_models
    else:
        frappe.log_error("No spaCy models found", "Doc2Sys spaCy Check")
        return False, []