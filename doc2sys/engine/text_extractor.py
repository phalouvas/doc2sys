from io import StringIO
import os
import frappe
import csv
import warnings
import base64
from .llm_processor import LLMProcessor  # Import the LLMProcessor

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
HAS_TESSERACT = False
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

# Try importing pytesseract
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    pass

from PIL import Image

class TextExtractor:
    def __init__(self, languages=None, user=None):
        """
        Initialize text extractor with specified languages
        
        Args:
            languages: List of language codes for OCR (e.g., ['eng', 'ell'])
                       If None, will fetch from user's Doc2Sys User Settings
            user: User for whom to load settings. If None, uses current user.
        """
        self.user = user or frappe.session.user
        
        # Get user settings
        self.user_settings = self._get_user_settings()
        
        # Determine OCR engine
        self.ocr_engine = "tesseract"  # Default
        if self.user_settings and self.user_settings.ocr_enabled:
            self.ocr_engine = self.user_settings.ocr_engine or "tesseract"
            
        # Initialize LLM processor if needed
        self.llm_processor = None
        if self.ocr_engine == "llm_api":
            try:
                self.llm_processor = LLMProcessor(user=self.user)
            except Exception as e:
                frappe.log_error(f"Failed to initialize LLM processor for OCR: {str(e)}", "Doc2Sys")
                self.ocr_engine = "tesseract"  # Fallback to tesseract on error
                
        # Get languages from settings if not provided
        if languages is None:
            self.languages = self._get_languages_from_settings()
        else:
            self.languages = languages if isinstance(languages, list) else ['eng']
            
        # Ensure we have at least English as fallback
        if not self.languages:
            self.languages = ['eng']
            
    def _get_user_settings(self):
        """Get user-specific settings document"""
        try:
            user_settings_list = frappe.get_all(
                'Doc2Sys User Settings',
                filters={'user': self.user},
                fields=['name']
            )
            
            if user_settings_list:
                return frappe.get_doc('Doc2Sys User Settings', user_settings_list[0].name)
        except Exception as e:
            frappe.log_error(f"Error fetching user settings for {self.user}: {str(e)}", "Doc2Sys")
            
        return None
            
    def _get_languages_from_settings(self):
        """Get configured OCR languages from user-specific settings"""
        languages = ['eng']  # Default to English
        
        try:
            if not self.user_settings:
                return languages
                
            # Check if OCR is enabled and using tesseract
            if self.user_settings.ocr_enabled and self.user_settings.ocr_engine == "tesseract":
                # Get enabled languages from the child table
                enabled_langs = [lang.language_code for lang in self.user_settings.ocr_languages if lang.enabled]
                
                # Use enabled languages if available, otherwise default to English
                if enabled_langs:
                    languages = enabled_langs
                    
            frappe.log_error(f"Using OCR languages for user {self.user}: {', '.join(languages)}", "Doc2Sys")
        except Exception as e:
            frappe.log_error(f"Error fetching OCR language settings for user {self.user}: {str(e)}", "Doc2Sys")
            
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
    
    def _check_tesseract_available(self):
        """Check if Tesseract OCR is available"""
        global HAS_TESSERACT
        
        if HAS_TESSERACT:
            return True
            
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            HAS_TESSERACT = True
            return True
        except ImportError:
            frappe.log_error("Pytesseract not installed - cannot perform OCR", "Doc2Sys")
            return False
        except Exception as e:
            frappe.log_error(f"Tesseract OCR not available: {str(e)}", "Doc2Sys")
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
    
    def _extract_text_using_llm(self, image_path):
        """Extract text from image using LLM API"""
        if not self.llm_processor:
            frappe.log_error("LLM processor not available for OCR", "Doc2Sys")
            return "OCR functionality not available. Cannot extract text from image."
            
        try:
            # Get the configured OCR model and endpoint
            model = self.user_settings.llm_ocr_model if self.user_settings else None
            
            # Create a prompt for OCR
            prompt = """
            Extract ALL text visible in this image. 
            Maintain the original format where possible, including paragraphs, bullet points, and tables.
            If there are multiple columns, process them from left to right, top to bottom.
            If text is in multiple languages, extract all text regardless of language.
            Only return the extracted text, no additional comments or explanations.
            """
            
            # Process the image using LLM
            result = self.llm_processor._make_api_request(
                f"{self.llm_processor.endpoint}/api/chat/completions",
                {
                    "model": model or self.llm_processor.model,
                    "temperature": 0.0,
                    "messages": [
                        {"role": "system", "content": "You are an OCR tool that extracts text from images."},
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": self._get_image_data_url(image_path)}}
                        ]}
                    ]
                }
            )
            
            if not result or "choices" not in result:
                return "Failed to extract text using LLM OCR."
                
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # If no text detected
            if not content.strip():
                return "No text detected in the image."
                
            return content.strip()
                
        except Exception as e:
            frappe.log_error(f"Error extracting text using LLM: {str(e)}", "Doc2Sys")
            return f"Error extracting text using LLM: {str(e)}"
    
    def _get_image_data_url(self, image_path):
        """Convert image to data URL format for LLM API"""
        try:
            file_extension = os.path.splitext(image_path)[1].lower()
            content_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.tiff': 'image/tiff'
            }.get(file_extension, 'image/jpeg')
            
            with open(image_path, 'rb') as img_file:
                base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                return f"data:{content_type};base64,{base64_image}"
        except Exception as e:
            frappe.log_error(f"Error converting image to data URL: {str(e)}", "Doc2Sys")
            return None
    
    def extract_text_from_image(self, image_path):
        """Extract text from image using configured OCR method"""
        # Use LLM-based OCR if configured
        if self.ocr_engine == "llm_api":
            return self._extract_text_using_llm(image_path)
            
        # Fallback to Tesseract OCR
        # Check if Tesseract OCR is available
        if not self._check_tesseract_available():
            return "OCR functionality not available. Cannot extract text from image."
        
        try:
            # Preprocess the image for better OCR results if OpenCV is available
            processed_path = self.preprocess_image(image_path)
            
            # Join languages with + for Tesseract format (e.g., eng+ell)
            lang_param = '+'.join(self.languages)
            
            # Configure OCR options
            config = f'--psm 3'  # Page segmentation mode 3: Fully automatic
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(Image.open(processed_path), lang=lang_param, config=config)
            
            # Clean up the temporary file if it was created
            if processed_path != image_path and os.path.exists(processed_path):
                try:
                    os.remove(processed_path)
                except:
                    pass
            
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
                # If no text extracted, use the configured OCR method
                if self.ocr_engine == "llm_api" and self.llm_processor:
                    # Try direct LLM processing of the PDF if possible
                    result = self._try_direct_llm_pdf_processing(pdf_path)
                    if result:
                        return result
                
                # Otherwise try the PDF to image conversion approach
                if self._check_tesseract_available() or (self.ocr_engine == "llm_api" and self.llm_processor):
                    return self._extract_text_from_pdf_using_ocr(pdf_path)
                else:
                    return f"No readable text found in PDF. Consider converting to images for OCR."
                
            return text.strip()
            
        except Exception as e:
            frappe.log_error(f"Error extracting text from PDF: {str(e)}", "Doc2Sys")
            return f"Error extracting text from PDF: {str(e)}"
    
    def _try_direct_llm_pdf_processing(self, pdf_path):
        """Attempt to process PDF directly with LLM if supported"""
        if self.ocr_engine != "llm_api" or not self.llm_processor:
            return None
            
        try:
            # Use LLM processor's file handling capabilities if available
            file_id = self.llm_processor.upload_file(pdf_path)
            if not file_id:
                return None
                
            # Create a prompt for extracting text
            prompt = "Extract ALL text content from this PDF document. Maintain the original format where possible."
            
            # Process using LLM
            result = self.llm_processor._make_api_request(
                f"{self.llm_processor.endpoint}/api/chat/completions",
                {
                    "model": self.llm_processor.model,
                    "temperature": 0.0,
                    "messages": [
                        {"role": "system", "content": "You are a tool that extracts text from PDF documents."},
                        {"role": "user", "content": prompt}
                    ],
                    "files": [{"type": "file", "id": file_id}]
                }
            )
            
            if not result or "choices" not in result:
                return None
                
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content.strip() else None
            
        except Exception as e:
            frappe.log_error(f"Error processing PDF directly with LLM: {str(e)}", "Doc2Sys")
            return None
    
    def _extract_text_from_pdf_using_ocr(self, pdf_path):
        """Extract text from PDF using OCR by converting to images first"""
        try:
            # Try importing pdf2image for PDF to image conversion
            import pdf2image
            pages = pdf2image.convert_from_path(pdf_path)
            
            text = ""
            for i, page in enumerate(pages):
                # Save page as temporary image
                temp_img = f"/tmp/pdf_page_{i}.png"
                page.save(temp_img, "PNG")
                
                # Extract text from the image using the configured OCR method
                page_text = self.extract_text_from_image(temp_img)
                text += page_text + "\n\n"
                
                # Remove temporary image
                try:
                    os.remove(temp_img)
                except:
                    pass
            
            return text.strip()
        except ImportError:
            return "PDF to image conversion not available. Please install pdf2image."
        except Exception as e:
            frappe.log_error(f"Error extracting text from PDF using OCR: {str(e)}", "Doc2Sys")
            return f"Error extracting text from PDF using OCR: {str(e)}"
    
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