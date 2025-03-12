// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Item', {
    refresh: function(frm) {
        // Add custom buttons or functionality here
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
            // Show a processing indicator
            frappe.show_alert({
                message: __('Extracting text from document...'),
                indicator: 'orange'
            });
        }
    }
});
