import frappe
from frappe.model.document import Document
import json
from doc2sys.integrations.utils import create_integration_log  # Add this import

class Doc2SysIntegrationLog(Document):
    def before_insert(self):
        """Ensure data is stored as proper JSON"""
        if self.data and isinstance(self.data, (dict, list)):
            self.data = json.dumps(self.data, indent=2, ensure_ascii=False)
    
    def get_parsed_data(self):
        """Return parsed JSON data"""
        if not self.data:
            return None
            
        try:
            return json.loads(self.data)
        except:
            return self.data
