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
                    freeze_message: __('Processing files from monitor folder...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Folder Processing Complete'),
                                message: __('Files from the monitor folder have been processed.'),
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

        // Add button to add common languages
        frm.add_custom_button(__('Add Common Languages'), function() {
            frappe.confirm(
                __('This will replace any existing language settings. Continue?'),
                function() {
                    // Call the server method to add common languages
                    frm.call({
                        doc: frm.doc,
                        method: 'add_common_languages',
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: __('Common languages added successfully'),
                                    indicator: 'green'
                                }, 5);
                                frm.refresh();
                            }
                        }
                    });
                }
            );
        }, __('OCR Settings'));
        
        // Add button to update language download status
        frm.add_custom_button(__('Check Downloaded Languages'), function() {
            frm.call({
                doc: frm.doc,
                method: 'update_language_download_status',
                freeze: true,
                freeze_message: __('Checking language models...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Language status updated'),
                            indicator: 'green'
                        }, 5);
                        frm.refresh();
                    }
                }
            });
        }, __('OCR Settings'));
        
        // Add button to download enabled language models
        frm.add_custom_button(__('Download Language Models'), function() {
            frappe.confirm(
                __('This will download models for all enabled languages. Continue?'),
                function() {
                    frm.call({
                        doc: frm.doc,
                        method: 'download_language_models',
                        freeze: true,
                        freeze_message: __('Downloading language models...'),
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                let results = r.message.results || [];
                                let successes = results.filter(res => res.success).length;
                                let failures = results.length - successes;
                                
                                frappe.show_alert({
                                    message: __(`Downloaded ${successes} languages, ${failures} failed`),
                                    indicator: failures > 0 ? 'orange' : 'green'
                                }, 5);
                                
                                // Show detailed results
                                let details = "";
                                results.forEach(result => {
                                    details += `<tr>
                                        <td>${result.language_code}</td>
                                        <td>${result.success ? 'Success' : 'Failed'}</td>
                                        <td>${result.message}</td>
                                    </tr>`;
                                });
                                
                                if (results.length > 0) {
                                    frappe.msgprint({
                                        title: __('Language Model Download Results'),
                                        message: `
                                            <table class="table table-bordered">
                                                <thead>
                                                    <tr>
                                                        <th>Language</th>
                                                        <th>Status</th>
                                                        <th>Message</th>
                                                    </tr>
                                                </thead>
                                                <tbody>${details}</tbody>
                                            </table>
                                        `,
                                        indicator: failures > 0 ? 'orange' : 'green'
                                    });
                                }
                                
                                frm.refresh();
                            }
                        }
                    });
                }
            );
        }, __('OCR Settings'));
        
        // Add button to list all downloaded languages
        frm.add_custom_button(__('List Downloaded Language Models'), function() {
            frm.call({
                doc: frm.doc,
                method: 'list_downloaded_languages',
                freeze: true,
                freeze_message: __('Checking language models...'),
                callback: function(r) {
                    if (r.message) {
                        let languages = r.message.languages || [];
                        let message = "";
                        
                        if (languages.length === 0) {
                            message = __('No language models found');
                        } else {
                            message = __(`Found ${languages.length} downloaded language models:<br>`) + 
                                      languages.join(', ') + '<br><br>' +
                                      __(`Model directory: ${r.message.model_dir}`);
                        }
                        
                        frappe.msgprint({
                            title: __('Downloaded Language Models'),
                            message: message,
                            indicator: languages.length > 0 ? 'green' : 'orange'
                        });
                    }
                }
            });
        }, __('OCR Settings'));
    },
    
    ocr_enabled: function(frm) {
        // When OCR is enabled/disabled, refresh form to show/hide related fields
        frm.refresh();
    }
});

frappe.ui.form.on('Doc2Sys OCR Language', {
    enabled: function(frm, cdt, cdn) {
        // When a language is enabled, show a message about downloading
        let row = locals[cdt][cdn];
        if (row.enabled && !row.model_downloaded) {
            frappe.show_alert({
                message: __(`Remember to download the model for ${row.language_name}`),
                indicator: 'blue'
            }, 5);
        }
    }
});
