from io import StringIO
import os
import frappe
import csv
import warnings

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
    def __init__(self, languages=None):
        """
        Initialize text extractor with specified languages
        
        Args:
            languages: List of language codes for OCR (e.g., ['en', 'fr', 'de'])
                       If None, will fetch from Doc2Sys Settings
        """
        # Get languages from settings if not provided
        if languages is None:
            self.languages = self._get_languages_from_settings()
        else:
            self.languages = languages if isinstance(languages, list) else ['en']
            
        # Ensure we have at least English as fallback
        if not self.languages:
            self.languages = ['en']
            
        self.reader = None
        
    def _get_languages_from_settings(self):
        """Get configured OCR languages from settings"""
        languages = ['en']  # Default to English
        
        try:
            # Get the settings document
            settings = frappe.get_doc("Doc2Sys Settings")
            
            # Check if OCR is enabled
            if settings.ocr_enabled:
                # Get enabled languages from the child table
                enabled_langs = [lang.language_code for lang in settings.ocr_languages if lang.enabled]
                
                # Use enabled languages if available, otherwise default to English
                if enabled_langs:
                    languages = enabled_langs
                    
            frappe.log_error(f"Using OCR languages: {', '.join(languages)}", "Doc2Sys")
        except Exception as e:
            frappe.log_error(f"Error fetching OCR language settings: {str(e)}", "Doc2Sys")
            
        return languages
    
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
            # Only import easyocr when actually needed
            import easyocr
            frappe.log_error(f"Initializing EasyOCR with languages: {', '.join(self.languages)}", "Doc2Sys")
            self.reader = easyocr.Reader(self.languages)
            HAS_OCR = True
            return True
        except ImportError:
            frappe.log_error("EasyOCR not available - cannot perform image OCR", "Doc2Sys")
            return False
        except Exception as e:
            frappe.log_error(f"Error initializing EasyOCR: {str(e)}", "Doc2Sys")
            return False
    
    def preprocess_image(self, image_path):
        """Preprocess image for better OCR results if OpenCV is available"""
        if not HAS_CV2:
            return image_path
        
        try:
            # Read the image
            image = cv2.imread(image_path)
            
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY, 11, 2)
            
            # Save processed image to a temporary file
            temp_path = f"{image_path}_processed.png"
            cv2.imwrite(temp_path, thresh)
            
            return temp_path
        except Exception as e:
            frappe.log_error(f"Error preprocessing image: {str(e)}", "Doc2Sys")
            return image_path
    
    def extract_text_from_image(self, image_path):
        """Extract text from image using EasyOCR with preprocessing"""
        # Try to load EasyOCR only when needed
        if not self._load_easyocr_if_needed():
            return "OCR functionality not available. Cannot extract text from image."
        
        try:
            # Preprocess the image for better OCR results if OpenCV is available
            processed_path = self.preprocess_image(image_path)
            
            # Extract text from the image
            results = self.reader.readtext(processed_path)
            
            # Clean up the temporary file if it was created
            if processed_path != image_path and os.path.exists(processed_path):
                try:
                    os.remove(processed_path)
                except:
                    pass
                
            # Compile results into text
            text = ""
            for detection in results:
                text += detection[1] + " "
            
            # If no text detected
            if not text.strip():
                return "No text detected in the image."
                
            return text.strip()
                
        except Exception as e:
            frappe.log_error(f"Error extracting text from image: {str(e)}", "Doc2Sys")
            return f"Error extracting text from image: {str(e)}"
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF file"""
        if not HAS_PDF:
            return "PDF extraction not available. Please install PyPDF2."
            
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
            
            if not text.strip():
                # If no text extracted, try OCR on the PDF as images
                return f"No readable text found in PDF. Consider converting to images for OCR."
                
            return text.strip()
            
        except Exception as e:
            frappe.log_error(f"Error extracting text from PDF: {str(e)}", "Doc2Sys")
            return f"Error extracting text from PDF: {str(e)}"
    
    def extract_text_from_word(self, docx_path):
        """Extract text from Word document"""
        if not HAS_DOCX:
            return "Word document extraction not available. Please install python-docx."
            
        try:
            doc = docx.Document(docx_path)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            
            return text.strip()
            
        except Exception as e:
            frappe.log_error(f"Error extracting text from Word doc: {str(e)}", "Doc2Sys")
            return f"Error extracting text from Word doc: {str(e)}"
    
    def extract_text_from_csv(self, csv_path):
        """Extract text from CSV file"""
        try:
            text = ""
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                for row in reader:
                    text += ", ".join(row) + "\n"
            
            return text.strip()
            
        except Exception as e:
            frappe.log_error(f"Error extracting text from CSV: {str(e)}", "Doc2Sys")
            return f"Error extracting text from CSV: {str(e)}"
    
    def extract_text_from_text_file(self, text_file_path):
        """Extract text from plain text file"""
        try:
            with open(text_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
                
        except Exception as e:
            frappe.log_error(f"Error extracting text from text file: {str(e)}", "Doc2Sys")
            return f"Error extracting text from text file: {str(e)}"