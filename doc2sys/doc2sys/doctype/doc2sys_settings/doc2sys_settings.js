// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Settings', {
    refresh: function(frm) {
        // Add Train ML Classifier button
        frm.add_custom_button(__('Train ML Classifier'), function() {
            frappe.call({
                method: 'doc2sys.doc2sys.doctype.doc2sys_settings.doc2sys_settings.train_ml_classifier',
                freeze: true,
                freeze_message: __('Training ML classifier... This may take some time.'),
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: __('ML Training Complete'),
                            message: __('The classifier has been trained with {0} documents.', [r.message.document_count]),
                            indicator: 'green'
                        });
                    } else {
                        frappe.msgprint({
                            title: __('ML Training Failed'),
                            message: __('Not enough documents available for training. Process more documents first.'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }, __('Machine Learning'));
        
        // Add Check Models button
        frm.add_custom_button(__('Check ML Models'), function() {
            frappe.call({
                method: 'doc2sys.doc2sys.doctype.doc2sys_settings.doc2sys_settings.check_ml_models',
                freeze: true,
                freeze_message: __('Checking ML models...'),
                callback: function(r) {
                    if (r.message && r.message.available) {
                        frappe.msgprint({
                            title: __('ML Models Available'),
                            message: __('Found spaCy models: {0}', [r.message.models.join(', ')]),
                            indicator: 'green'
                        });
                    } else {
                        frappe.msgprint({
                            title: __('ML Models Not Found'),
                            message: __('No spaCy models are available. Machine learning features will be limited.'),
                            indicator: 'orange'
                        });
                    }
                }
            });
        }, __('Machine Learning'));
    }
});
