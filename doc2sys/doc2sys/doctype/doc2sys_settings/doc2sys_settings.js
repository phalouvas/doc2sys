// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Settings', {
    refresh: function(frm) {
        
        // Add manual folder processing button
        if (frm.doc.monitoring_enabled) {
            frm.add_custom_button(__('Process Folder Now'), function() {
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_settings.doc2sys_settings.run_folder_monitor',
                    freeze: true,
                    freeze_message: __('Processing files from source folder...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Folder Processing Complete'),
                                message: __('Files from the source folder have been processed.'),
                                indicator: 'green'
                            });
                        } else {
                            frappe.msgprint({
                                title: __('Folder Processing Failed'),
                                message: r.message ? r.message.message : __('Unknown error'),
                                indicator: 'red'
                            });
                        }
                    }
                });
            }, __('Folder Monitor'));
        }
    }
});
