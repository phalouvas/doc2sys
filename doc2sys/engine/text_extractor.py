import os
import frappe
import csv
import warnings
from io import StringIO

# Suppress PyPDF2 deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyPDF2")

# Import PyPDF2 with error handling
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

# Make all dependency imports conditional
HAS_DOCX = False
HAS_PDF = PdfReader is not None
HAS_OCR = False
HAS_CV2 = False

# Try importing docx
try:
    import docx
    HAS_DOCX = True
except ImportError:
    pass

# Try importing OpenCV
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    pass

class TextExtractor:
    def __init__(self, languages=['en']):
        self.languages = languages
        self.reader = None
        
        # Lazy import EasyOCR only when needed to avoid startup errors
        if not HAS_OCR:
            # Log this once, not every time we create an extractor
            frappe.log_error("OCR libraries not fully available - some functionality limited", "Doc2Sys Setup")
    
    def extract_text(self, file_path):
        """Extract text from various file types"""
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
            
        file_extension = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif']:
                return self.extract_text_from_image(file_path)
            elif file_extension == '.pdf':
                return self.extract_text_from_pdf(file_path)
            elif file_extension in ['.docx', '.doc']:
                return self.extract_text_from_word(file_path)
            elif file_extension == '.csv':
                return self.extract_text_from_csv(file_path)
            elif file_extension in ['.txt', '.md', '.json']:
                return self.extract_text_from_text_file(file_path)
            else:
                return f"Text extraction not supported for {file_extension} files"
        except Exception as e:
            frappe.log_error(f"Error extracting text from {file_path}: {str(e)}", "Doc2Sys")
            return f"Error extracting text: {str(e)}"
    
    def _load_easyocr_if_needed(self):
        """Lazy loading of EasyOCR to avoid startup errors"""
        global HAS_OCR
        
        if self.reader is not None:
            return True
            
        try:
            import easyocr
            self.reader = easyocr.Reader(self.languages)
            HAS_OCR = True
            return True
        except ImportError:
            frappe.log_error("EasyOCR not available - cannot perform image OCR", "Doc2Sys")
            return False
        except Exception as e:
            frappe.log_error(f"Error initializing EasyOCR: {str(e)}", "Doc2Sys")
            return False
    
    def extract_text_from_image(self, image_path):
        """Extract text from image using EasyOCR with preprocessing"""
        # Try to load EasyOCR only when needed
        if not self._load_easyocr_if_needed():
            return "OCR functionality not available. Cannot extract text from image."
        
        try:
            # Perform OCR directly without preprocessing first
            results = self.reader.readtext(image_path)
            
            # Extract text from results
            text = ' '.join([result[1] for result in results])
            return text
        except Exception as e:
            frappe.log_error(f"Image text extraction error: {str(e)}", "Doc2Sys")
            return f"Error extracting text from image: {str(e)}"
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF file"""
        if not HAS_PDF:
            return "PDF extraction not available. Please install PyPDF2."
            
        try:
            text = []
            pdf_reader = PdfReader(pdf_path)
            
            for page in pdf_reader.pages:
                page_text = page.extract_text() or ""
                text.append(page_text)
            
            return "\n\n".join(text)
        except Exception as e:
            frappe.log_error(f"PDF text extraction error: {str(e)}", "Doc2Sys")
            return f"Error extracting text from PDF: {str(e)}"
    
    def extract_text_from_word(self, docx_path):
        """Extract text from Word document"""
        if not HAS_DOCX:
            return "Word document extraction not available. Please install python-docx."
            
        try:
            doc = docx.Document(docx_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            frappe.log_error(f"Word document text extraction error: {str(e)}", "Doc2Sys")
            return f"Error extracting text from Word document: {str(e)}"
    
    def extract_text_from_csv(self, csv_path):
        """Extract text from CSV file"""
        try:
            text = []
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as csv_file:
                csv_reader = csv.reader(csv_file)
                for row in csv_reader:
                    text.append(" | ".join(row))
            
            return "\n".join(text)
        except Exception as e:
            frappe.log_error(f"CSV text extraction error: {str(e)}", "Doc2Sys")
            return f"Error extracting text from CSV: {str(e)}"
    
    def extract_text_from_text_file(self, text_file_path):
        """Extract text from plain text file"""
        try:
            with open(text_file_path, 'r', encoding='utf-8', errors='replace') as file:
                return file.read()
        except Exception as e:
            frappe.log_error(f"Text file extraction error: {str(e)}", "Doc2Sys")
            return f"Error extracting text from file: {str(e)}"