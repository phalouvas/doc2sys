import os
import json
import frappe
from .utils import logger

# Check for optional dependencies
SKLEARN_AVAILABLE = False
NUMPY_AVAILABLE = False
SPACY_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    logger.warning("NumPy not available, ML classification will be limited")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.svm import LinearSVC
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn not available, ML classification will be limited")

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    logger.warning("spaCy not available, NLP features will be limited")

try:
    import pickle
except ImportError:
    logger.warning("pickle not available, model saving/loading will be disabled")

class MLDocumentClassifier:
    """Classifies documents using ML/NLP techniques"""
    
    def __init__(self, config=None):
        """Initialize with optional configuration"""
        self.config = config
        self.logger = logger
        self.nlp = None
        self.classifier = None
        
        # Only initialize ML components if dependencies are available
        if SPACY_AVAILABLE:
            self.nlp = self._load_spacy_model()
            
        if SKLEARN_AVAILABLE and NUMPY_AVAILABLE:
            self.classifier = self._load_classifier()
    
    def _load_spacy_model(self):
        """Load spaCy NLP model"""
        if not SPACY_AVAILABLE:
            return None
            
        try:
            # First try loading the medium-sized model
            self.logger.info("Attempting to load spaCy model: en_core_web_md")
            return spacy.load("en_core_web_md")
        except Exception as e:
            self.logger.error(f"Error loading medium spaCy model: {str(e)}")
            
            # Try loading from direct path if installed via pip
            try:
                self.logger.info("Attempting to load spaCy model from pip package")
                return spacy.load("en-core-web-md")
            except Exception:
                # Try loading small model as fallback
                try:
                    self.logger.info("Attempting to load small spaCy model as fallback")
                    return spacy.load("en_core_web_sm")
                except Exception as e2:
                    self.logger.error(f"Failed to load any spaCy model: {str(e2)}")
                    
                    # Last resort - load blank model
                    self.logger.info("Loading blank spaCy model as last resort")
                    return spacy.blank("en")
    
    def _load_classifier(self):
        """Load or create document classifier"""
        if not SKLEARN_AVAILABLE or not NUMPY_AVAILABLE:
            return None
            
        model_path = self._get_model_path()
        
        if os.path.exists(model_path):
            try:
                with open(model_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                self.logger.error(f"Error loading classifier model: {str(e)}")
        
        # If no model exists or loading failed, create a new one
        return self._create_classifier()
    
    def _get_model_path(self):
        """Get path for storing the model"""
        try:
            # Use the current site context
            return os.path.join(frappe.get_site_path("private", "files", "doc2sys_classifier.pkl"))
        except Exception as e:
            # Fallback if there's an error
            self.logger.error(f"Error getting model path: {str(e)}")
            site_name = frappe.local.site
            return os.path.join(frappe.utils.get_bench_path(), "sites", site_name, 
                              "private", "files", "doc2sys_classifier.pkl")
    
    def _create_classifier(self):
        """Create a new document classifier"""
        if not SKLEARN_AVAILABLE:
            return None
            
        # Create a pipeline with TF-IDF and linear SVM
        classifier = Pipeline([
            ('tfidf', TfidfVectorizer(max_features=10000, ngram_range=(1, 2))),
            ('clf', OneVsRestClassifier(LinearSVC()))
        ])
        
        # Try to train the classifier immediately with any available data
        try:
            # Get existing document types to create a minimal training set
            doc_types = frappe.get_all("Doc2Sys Document Type", 
                                      fields=["document_type", "keywords"],
                                      filters={"enabled": 1})
            
            # If we have some document types, create a minimal synthetic dataset
            if doc_types:
                self.logger.info("Creating initial training data from document types")
                
                # Create synthetic training data from the keywords
                train_texts = []
                train_labels = []
                
                for dt in doc_types:
                    if dt.keywords:
                        keywords = [k.strip() for k in dt.keywords.split(',') if k.strip()]
                        if keywords:
                            # Use the keywords as training examples
                            for kw in keywords:
                                train_texts.append(f"Document containing {kw}")
                                train_labels.append(dt.document_type)
                            
                            # Add a synthetic document with all keywords
                            train_texts.append(" ".join(keywords))
                            train_labels.append(dt.document_type)
                
                # Train with synthetic data if we have examples
                if train_texts and train_labels:
                    classifier.fit(train_texts, train_labels)
                    self.logger.info(f"Initialized classifier with {len(train_texts)} synthetic examples")
        except Exception as e:
            self.logger.error(f"Error creating initial training data: {str(e)}")
        
        return classifier
    
    def train_classifier(self):
        """Train the document classifier with available data"""
        if not SKLEARN_AVAILABLE or not NUMPY_AVAILABLE:
            self.logger.warning("ML libraries not available, can't train classifier")
            return False
            
        try:
            # Check if the required DocTypes exist
            if not frappe.db.exists("DocType", "Doc2Sys Item") or not frappe.db.exists("DocType", "Doc2Sys Document Type"):
                self.logger.warning("Required DocTypes don't exist yet, can't train classifier")
                return False
                
            # Check if document_type field exists in Doc2Sys Item
            has_document_type = False
            try:
                meta = frappe.get_meta("Doc2Sys Item")
                has_document_type = meta.has_field("document_type")
            except:
                has_document_type = False
                
            if not has_document_type:
                self.logger.warning("Doc2Sys Item doesn't have document_type field yet")
                return False
                
            # Get training data from Doc2Sys Item with known document types
            items = frappe.get_all(
                "Doc2Sys Item", 
                filters={"document_type": ["!=", ""]},
                fields=["text_content", "document_type"]
            )
            
            # Check if we have enough data
            if len(items) < 5:
                self.logger.warning(f"Not enough training data: {len(items)} samples")
                return False
            
            # Prepare training data
            texts = [item.text_content for item in items if item.text_content]
            labels = [item.document_type for item in items if item.text_content]
            
            # Train the classifier
            self.classifier.fit(texts, labels)
            
            # Save the model
            model_path = self._get_model_path()
            model_dir = os.path.dirname(model_path)
            
            # Ensure directory exists
            if not os.path.exists(model_dir):
                os.makedirs(model_dir, exist_ok=True)

            with open(model_path, 'wb') as f:
                pickle.dump(self.classifier, f)
            
            self.logger.info(f"Trained classifier with {len(texts)} samples")
            return True
            
        except Exception as e:
            self.logger.error(f"Error training classifier: {str(e)}")
            return False
    
    def classify_document(self, text):
        """
        Classify document using ML/NLP
        
        Args:
            text: Document text content
            
        Returns:
            dict: Classification result with document type and confidence
        """
        # Fall back to basic classification if ML dependencies aren't available
        if not SKLEARN_AVAILABLE or not NUMPY_AVAILABLE:
            return self._basic_classification(text)
            
        # Check if classifier exists and is trained
        if self.classifier is None:
            self.logger.warning("Classifier not initialized, falling back to rule-based classification")
            return self._basic_classification(text)
        
        # Check if the classifier has been fitted (trained)
        try:
            # This is a simple check to see if the classifier has been trained
            # If it has classes_ attribute, it's likely been trained
            if not hasattr(self.classifier, 'classes_') or not self.classifier.classes_.size:
                self.logger.warning("Classifier not trained yet, attempting to train now")
                
                # Try to train the classifier with available data
                trained = self.train_classifier()
                if not trained:
                    self.logger.warning("Could not train classifier, falling back to rule-based classification")
                    return self._basic_classification(text)
        except Exception as e:
            self.logger.error(f"Error checking classifier training state: {str(e)}")
            return self._basic_classification(text)
        
        # Process text with spaCy for feature extraction
        if self.nlp:
            doc = self.nlp(text[:100000])  # Limit text size for performance
            
            # Extract key features
            key_phrases = [ent.text for ent in doc.ents if ent.label_ in ["ORG", "DATE", "MONEY"]]
            
            # Add key features back to text for better classification
            augmented_text = text + " " + " ".join(key_phrases)
        else:
            augmented_text = text
        
        try:
            # Try to classify with the trained model
            if hasattr(self.classifier, 'predict_proba'):
                # Get prediction probabilities if available
                proba = self.classifier.predict_proba([augmented_text])[0]
                doc_type_index = np.argmax(proba)
                confidence = proba[doc_type_index]
                doc_type = self.classifier.classes_[doc_type_index]
            else:
                # Otherwise just get the prediction
                doc_type = self.classifier.predict([augmented_text])[0]
                confidence = 0.8  # Default confidence
                
            # If confidence is too low, mark as unknown
            if confidence < 0.3:
                return {
                    "document_type": "unknown",
                    "confidence": confidence,
                    "target_doctype": None
                }
                
            # Get target doctype from document type
            target_doctype = self._get_target_doctype(doc_type)
                
            return {
                "document_type": doc_type,
                "confidence": float(confidence),
                "target_doctype": target_doctype
            }
        except Exception as e:
            self.logger.error(f"Classification error: {str(e)}")
            return self._basic_classification(text)
    
    def _basic_classification(self, text):
        """Basic rule-based classification when ML isn't available"""
        try:
            # Check if Doc2Sys Document Type exists
            if frappe.db.exists("DocType", "Doc2Sys Document Type"):
                # Get document types from settings
                doc_types = frappe.get_all("Doc2Sys Document Type", 
                                          fields=["document_type", "keywords", "target_doctype"],
                                          filters={"enabled": 1})
                
                best_match = None
                best_score = 0
                text_lower = text.lower()
                
                for dt in doc_types:
                    if not dt.keywords:
                        continue
                        
                    keywords = [k.strip().lower() for k in dt.keywords.split(",") if k.strip()]
                    if not keywords:
                        continue
                        
                    # Count keyword matches
                    matches = sum(1 for kw in keywords if kw in text_lower)
                    score = matches / len(keywords) if len(keywords) > 0 else 0
                    
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "document_type": dt.document_type,
                            "confidence": score,
                            "target_doctype": dt.target_doctype
                        }
                
                if best_match:
                    return best_match
        except Exception as e:
            self.logger.error(f"Error in basic classification: {str(e)}")
        
        # Default return if no match or error
        return {
            "document_type": "unknown",
            "confidence": 0.0,
            "target_doctype": None
        }
    
    def _get_target_doctype(self, doc_type):
        """Get target doctype for a document type"""
        try:
            # Query for Doc2Sys Document Type where document_type field matches
            doc_types = frappe.get_all(
                "Doc2Sys Document Type", 
                filters={"document_type": doc_type},
                fields=["target_doctype"]
            )
            
            if doc_types:
                return doc_types[0].target_doctype
            
            # If not found by document_type, try direct name lookup as fallback
            # (This is the original approach but should rarely be needed)
            try:
                doc_type_config = frappe.get_doc("Doc2Sys Document Type", doc_type)
                return doc_type_config.target_doctype
            except:
                pass
                
            return None
        except Exception as e:
            self.logger.error(f"Error getting target DocType: {str(e)}")
            return None