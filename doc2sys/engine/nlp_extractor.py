import re
import frappe
from datetime import datetime
import json
from .utils import logger

# Check for optional dependencies
SPACY_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    logger.warning("spaCy not available, NLP features will be limited")

class NLPDataExtractor:
    """Extracts structured data from documents using NLP"""
    
    def __init__(self, config=None):
        """Initialize with optional configuration"""
        self.config = config
        self.logger = logger
        self.nlp = None
        self.custom_patterns = self._load_custom_patterns()
        
        # Only initialize NLP components if dependencies are available
        if SPACY_AVAILABLE:
            self.nlp = self._load_spacy_model()
    
    def _load_spacy_model(self):
        """Load spaCy NLP model"""
        if not SPACY_AVAILABLE:
            return None
            
        try:
            return spacy.load("en_core_web_md")
        except Exception as e:
            self.logger.error(f"Error loading spaCy model: {str(e)}")
            # Try to fallback to small model
            try:
                return spacy.load("en_core_web_sm")
            except:
                self.logger.error("Failed to load any spaCy model")
                return None
    
    def _load_custom_patterns(self):
        """Load custom extraction patterns from settings"""
        patterns = {}
        try:
            # Check if DocType exists first
            if not frappe.db.exists("DocType", "Doc2Sys Extraction Field"):
                self.logger.warning("Doc2Sys Extraction Field DocType doesn't exist yet")
                return {}
                
            # Get patterns from Doc2Sys Extraction Field
            fields = frappe.get_all("Doc2Sys Extraction Field",
                                  fields=["field_name", "regex_pattern", "parent_document_type"])
            
            for field in fields:
                if field.regex_pattern:
                    doc_type = field.parent_document_type
                    if doc_type not in patterns:
                        patterns[doc_type] = {}
                    patterns[doc_type][field.field_name] = field.regex_pattern
                    
            return patterns
        except Exception as e:
            self.logger.error(f"Error loading custom patterns: {str(e)}")
            return {}
    
    def extract_data(self, text, document_type):
        """
        Extract structured data from document using NLP
        
        Args:
            text: Document text content
            document_type: Type of document
            
        Returns:
            dict: Extracted data fields
        """
        extracted_data = {}
        
        # Use spaCy if available
        if SPACY_AVAILABLE and self.nlp:
            doc = self.nlp(text[:100000])  # Limit size for performance
            extracted_data = self._extract_basic_entities(doc)
        
        # Apply custom extraction patterns (works without spaCy too)
        custom_extracted = self._apply_custom_extraction(text, document_type)
        extracted_data.update(custom_extracted)
        
        # Extract specific fields based on document type using regex patterns
        if document_type == "Invoice":
            extracted_data.update(self._extract_invoice_data(text))
        elif document_type == "Receipt":
            extracted_data.update(self._extract_receipt_data(text))
            
        return extracted_data
        
    def _extract_basic_entities(self, doc):
        """Extract basic entities from spaCy doc"""
        if not SPACY_AVAILABLE or not doc:
            return {}
            
        entities = {}
        
        # Extract organizations
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
        if orgs:
            entities["organizations"] = orgs
        
        # Extract dates
        dates = []
        for ent in doc.ents:
            if ent.label_ == "DATE":
                # Try to parse date
                try:
                    # This is a simplified approach - might need a more robust date parser
                    date_formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(ent.text, fmt)
                            dates.append(date_obj.strftime("%Y-%m-%d"))
                            break
                        except:
                            continue
                except:
                    dates.append(ent.text)
        
        if dates:
            entities["dates"] = dates
            # Try to identify document date (usually the first date)
            if dates:
                entities["document_date"] = dates[0]
        
        # Extract money amounts
        amounts = [ent.text for ent in doc.ents if ent.label_ == "MONEY"]
        if amounts:
            entities["amounts"] = amounts
            # Try to find the largest amount (likely to be the total)
            try:
                numeric_amounts = []
                for amount in amounts:
                    # Clean amount string and convert to float
                    clean_amount = re.sub(r'[^\d.]', '', amount)
                    if clean_amount:
                        numeric_amounts.append(float(clean_amount))
                
                if numeric_amounts:
                    entities["total_amount"] = max(numeric_amounts)
            except:
                pass
                
        return entities
    
    def _apply_custom_extraction(self, text, document_type):
        """Apply custom extraction patterns"""
        extracted = {}
        
        # Get patterns for this document type
        patterns = self.custom_patterns.get(document_type, {})
        
        # Apply each pattern
        for field_name, pattern in patterns.items():
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    value = match.group(1).strip() if match.groups() else match.group(0).strip()
                    extracted[field_name] = value
            except Exception as e:
                self.logger.error(f"Error applying pattern for {field_name}: {str(e)}")
                
        return extracted
    
    def _extract_invoice_data(self, text):
        """Extract specific data for invoices using regex patterns"""
        data = {}
        
        # Invoice number - look for specific patterns
        invoice_patterns = [
            r'invoice\s*(?:no|number|#)[:\.\s]*(\w+[-/\w]*)',
            r'invoice[:\.\s]*(\w+[-/\w]*)',
            r'bill\s*(?:no|number)[:\.\s]*(\w+[-/\w]*)'
        ]
        
        for pattern in invoice_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["invoice_number"] = match.group(1)
                break
                
        # Due date - look for patterns indicating payment due date
        due_patterns = [
            r'due\s*(?:date|on)[:\.\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            r'payment\s*due[:\.\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})'
        ]
        
        for pattern in due_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["due_date"] = match.group(1)
                break
        
        # Look for tax/VAT information
        tax_patterns = [
            r'vat[:\.\s]*(\d+[,\.\d]*%?)',
            r'tax[:\.\s]*(\d+[,\.\d]*%?)',
            r'vat\s*amount[:\.\s]*([€$£]?\s?\d+[,\.\d]*)'
        ]
        
        for pattern in tax_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["tax_amount"] = match.group(1)
                break
        
        return data
    
    def _extract_receipt_data(self, text):
        """Extract specific data for receipts using regex patterns"""
        data = {}
        
        # Receipt number
        receipt_patterns = [
            r'receipt\s*(?:no|number|#)[:\.\s]*(\w+[-/\w]*)',
            r'receipt[:\.\s]*(\w+[-/\w]*)'
        ]
        
        for pattern in receipt_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data["receipt_number"] = match.group(1)
                break
        
        # Extract merchant/store name - use regex for basic extraction
        merchant_patterns = [
            r'^([A-Z][A-Z\s&]+)$',  # All caps company name at start of line
            r'^(.*?)\s*(?:receipt|invoice)'  # Text before "receipt" or "invoice"
        ]
        
        for pattern in merchant_patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
            if matches:
                # Take the first match that's a reasonable length
                for match in matches:
                    if 3 < len(match.strip()) < 40:  # Reasonable length for company name
                        data["merchant"] = match.strip()
                        break
                if "merchant" in data:
                    break
        
        return data