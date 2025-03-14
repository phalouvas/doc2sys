// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Item', {
    refresh: function(frm) {
        // Add custom buttons or functionality here
        // Add Reprocess button if a document is attached
        if(frm.doc.single_file) {
            frm.add_custom_button(__('Reprocess Document'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Reprocessing document...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'reprocess_document',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Document reprocessing completed'),
                                indicator: 'green'
                            }, 3);
                            frm.refresh();
                        }
                    },
                    error: function() {
                        // Make sure to unfreeze UI even if there's an error
                        frappe.dom.unfreeze();
                    }
                });
            }, __('Actions'));
        }
    },
    
    single_file: function(frm) {
        // When file is uploaded, show a message that processing will begin on save
        if(frm.doc.single_file) {
            frappe.show_alert({
                message: __('File attached. Text will be extracted when the document is saved.'),
                indicator: 'blue'
            }, 5);
        }
    },
    
    before_save: function(frm) {
        if(frm.doc.single_file && (frm.doc.__unsaved || frm.doc.text_content === '' || 
           frm.doc.text_content === undefined)) {
            // Show a full screen processing overlay
            frappe.dom.freeze(__('Extracting text from document...'));
        }
    },
    
    after_save: function(frm) {
        // Unfreeze UI after save is complete
        frappe.dom.unfreeze();
    }
});
