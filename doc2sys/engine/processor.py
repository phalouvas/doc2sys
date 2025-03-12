"""
Main processing logic for the document processing engine.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import frappe
from .config import EngineConfig
from .utils import logger, get_file_extension, is_supported_file_type
from .exceptions import ProcessingError, UnsupportedDocumentError

# Import conditional - will be used if available
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

class DocumentProcessor:
    """
    Core document processing class that handles document transformation
    and data extraction.
    """
    
    def __init__(self, config=None):
        """
        Initialize the document processor with optional configuration.
        
        Args:
            config: Optional configuration object or dict
        """
        self.config = config or EngineConfig()
        self.logger = logger
        
        # Check if required tools are installed
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required external tools are installed"""
        try:
            # Check poppler-utils (pdftotext)
            subprocess.run(["pdftotext", "-v"], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE, 
                          check=False)
            
            # Check tesseract-ocr
            subprocess.run(["tesseract", "--version"], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE, 
                          check=False)
        except FileNotFoundError as e:
            self.logger.error(f"Required dependency not found: {str(e)}")
            frappe.log_error(f"Doc2Sys missing dependency: {str(e)}", 
                            "Please install poppler-utils and tesseract-ocr")
    
    def process_document(self, document_path, options=None):
        """
        Process a document and extract structured data.
        
        Args:
            document_path: Path to the document file
            options: Optional processing options
            
        Returns:
            Extracted data in structured format
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info(f"Processing document: {document_path}")
            options = options or {}
            
            # Validate file exists
            if not os.path.exists(document_path):
                raise ProcessingError(f"Document not found: {document_path}")
            
            # Check if file type is supported
            if not is_supported_file_type(document_path, self.config.supported_file_types):
                raise UnsupportedDocumentError(f"Unsupported file type: {get_file_extension(document_path)}")
            
            # Extract text from document
            extracted_text = self.extract_text(document_path)
            
            # Process the extracted text
            # (Future: Add more sophisticated processing here)
            
            result = {
                "status": "success",
                "file_path": document_path,
                "file_type": get_file_extension(document_path),
                "text_length": len(extracted_text),
                "extracted_text": extracted_text[:1000] + ("..." if len(extracted_text) > 1000 else ""),
                "data": {}
            }
            
            return result
        except Exception as e:
            self.logger.error(f"Error processing document: {str(e)}")
            raise ProcessingError(f"Failed to process document: {str(e)}")
    
    def extract_text(self, file_path):
        """Extract text from a document based on its file type"""
        file_ext = get_file_extension(file_path)
        
        if file_ext == 'pdf':
            return self._extract_text_from_pdf(file_path)
        elif file_ext in ['jpg', 'jpeg', 'png', 'tif', 'tiff', 'bmp']:
            return self._extract_text_with_ocr(file_path)
        elif file_ext in ['txt', 'md', 'csv']:
            return self._extract_text_from_text_file(file_path)
        elif file_ext in ['docx']:
            return self._extract_text_from_docx(file_path)
        else:
            raise UnsupportedDocumentError(f"Unsupported file type for text extraction: {file_ext}")
    
    def _extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF using poppler-utils"""
        self.logger.info(f"Extracting text from PDF: {pdf_path}")
        
        # Create a temporary file for output
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
            temp_txt_path = temp_file.name
        
        try:
            # Run pdftotext to extract text
            cmd = ["pdftotext", "-layout", "-enc", "UTF-8", pdf_path, temp_txt_path]
            process = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            
            # Read the extracted text
            with open(temp_txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # If text is empty and OCR is enabled, try OCR instead
            if not text.strip() and self.config.ocr_enabled:
                self.logger.info(f"No text found in PDF, attempting OCR: {pdf_path}")
                return self._extract_text_from_pdf_with_ocr(pdf_path)
                
            return text
        except subprocess.CalledProcessError as e:
            self.logger.error(f"pdftotext error: {e.stderr}")
            raise ProcessingError(f"Failed to extract text from PDF: {e.stderr}")
        finally:
            # Clean up temporary file
            if os.path.exists(temp_txt_path):
                os.unlink(temp_txt_path)
    
    def _extract_text_from_pdf_with_ocr(self, pdf_path):
        """Extract text from a PDF using OCR by converting to images first"""
        if not self.config.ocr_enabled:
            self.logger.warning("OCR is disabled in settings")
            return ""
            
        if not PDF2IMAGE_AVAILABLE:
            self.logger.error("pdf2image library not installed")
            raise ProcessingError("pdf2image library is required to process image-only PDFs")
            
        self.logger.info(f"Converting PDF to images for OCR: {pdf_path}")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Convert PDF pages to images
                images = convert_from_path(
                    pdf_path,
                    output_folder=temp_dir,
                    fmt='png',
                    dpi=300  # Higher DPI for better OCR results
                )
                
                all_text = []
                
                # Process each page image with OCR
                for i, img_path in enumerate(sorted([os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith('.png')])):
                    self.logger.info(f"Processing PDF page {i+1} with OCR")
                    page_text = self._extract_text_with_ocr(img_path)
                    all_text.append(f"--- Page {i+1} ---\n{page_text}")
                
                # Combine text from all pages
                return "\n\n".join(all_text)
                
        except Exception as e:
            self.logger.error(f"Error in PDF OCR processing: {str(e)}")
            raise ProcessingError(f"Failed to process PDF with OCR: {str(e)}")
    
    def _extract_text_with_ocr(self, image_path):
        """Extract text from images using Tesseract OCR"""
        if not self.config.ocr_enabled:
            self.logger.warning("OCR is disabled in settings")
            return ""
        
        self.logger.info(f"Extracting text with OCR: {image_path}")
        
        # Create a temporary file for output
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
            temp_txt_path = temp_file.name
        
        try:
            # Run tesseract for OCR with configured languages
            output_base = os.path.splitext(temp_txt_path)[0]
            
            # Join language codes with '+' for tesseract
            lang_param = '+'.join(self.config.ocr_languages)
            
            # Build command with language parameter
            cmd = ["tesseract", image_path, output_base, "-l", lang_param]
            
            self.logger.info(f"Running OCR with languages: {lang_param}")
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            
            # Tesseract automatically adds .txt extension
            actual_output = output_base + ".txt"
            
            # Read the extracted text
            with open(actual_output, 'r', encoding='utf-8') as f:
                text = f.read()
                
            return text
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Tesseract OCR error: {e.stderr}")
            raise ProcessingError(f"Failed to extract text with OCR: {e.stderr}")
        finally:
            # Clean up temporary files
            if os.path.exists(temp_txt_path + '.txt'):
                os.unlink(temp_txt_path + '.txt')
                
    def _extract_text_from_text_file(self, file_path):
        """Extract text from plain text files"""
        self.logger.info(f"Reading text file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try different encoding if UTF-8 fails
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
                
    def _extract_text_from_docx(self, file_path):
        """Extract text from DOCX files"""
        self.logger.info(f"Extracting text from DOCX: {file_path}")
        
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except ImportError:
            self.logger.error("python-docx library not installed")
            raise ProcessingError("python-docx library is required to process DOCX files")