# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from doc2sys.engine.ml_classifier import MLDocumentClassifier

class Doc2SysSettings(Document):
    def validate(self):
        """Validate settings"""
        if self.max_file_size_mb <= 0:
            frappe.throw("Maximum file size must be greater than 0")
            
    def get_supported_file_extensions(self):
        """Return list of supported file extensions"""
        return [ft.file_extension.lower().strip() for ft in self.supported_file_types if ft.file_extension]
    
    def get_max_file_size_bytes(self):
        """Return max file size in bytes"""
        return self.max_file_size_mb * 1024 * 1024

@frappe.whitelist()
def train_ml_classifier():
    """Train the machine learning classifier with existing documents"""
    try:
        # Initialize the classifier
        classifier = MLDocumentClassifier()
        
        # Train the model
        success = classifier.train_classifier()
        
        if success:
            # Get the count of documents used for training
            doc_count = len(frappe.get_all(
                "Doc2Sys Item", 
                filters={"document_type": ["!=", ""]},
                limit=1000
            ))
            
            frappe.log_error(f"ML Classifier trained with {doc_count} documents", "Doc2Sys ML Training")
            return {"success": True, "document_count": doc_count}
        else:
            return None
    except Exception as e:
        frappe.log_error(f"Error training ML classifier: {str(e)}", "Doc2Sys ML Training Error")
        return None

@frappe.whitelist()
def check_ml_models():
    """Check if ML models are available"""
    from doc2sys.engine.utils import check_spacy_model_availability
    
    has_models, available_models = check_spacy_model_availability()
    
    return {
        "available": has_models,
        "models": available_models
    }
