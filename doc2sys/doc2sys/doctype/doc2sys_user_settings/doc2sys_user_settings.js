// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys User Settings', {
    refresh: function(frm) {

        // Add manual folder processing button
        if (frm.doc.monitoring_enabled) {
            frm.add_custom_button(__('Process Folder Now'), function() {
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.process_user_folder',
                    args: {
                        user_settings: frm.doc.name
                    },
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

        // Add button to delete unused language models
        frm.add_custom_button(__('Delete Unused Models'), function() {
            frappe.confirm(
                __('This will permanently delete language models that are not enabled in settings. Continue?'),
                function() {
                    frm.call({
                        doc: frm.doc,
                        method: 'delete_not_enabled_language_models',
                        freeze: true,
                        freeze_message: __('Deleting unused language models...'),
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                let results = r.message.results || [];
                                let successes = results.filter(res => res.success).length;
                                let failures = results.length - successes;
                                
                                if (results.length === 0) {
                                    frappe.show_alert({
                                        message: __('No unused language models to delete'),
                                        indicator: 'blue'
                                    }, 5);
                                } else {
                                    frappe.show_alert({
                                        message: __(`Deleted ${successes} language models, ${failures} failed`),
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
                                    
                                    frappe.msgprint({
                                        title: __('Language Model Deletion Results'),
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
        
        // Add button to test integration connection
        frm.add_custom_button(__('Test Selected Integrations'), function() {
            const selected = frm.get_selected();
            if(!selected.user_integrations || selected.user_integrations.length === 0) {
                frappe.throw(__("Please select at least one integration row first"));
                return;
            }
            
            frappe.show_alert({
                message: __(`Testing ${selected.user_integrations.length} connection(s)...`),
                indicator: 'blue'
            });
            
            frappe.call({
                method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.test_integration_connection',
                args: {
                    user_settings: frm.doc.name,
                    selected: selected
                },
                freeze: true,
                freeze_message: __('Testing integrations...'),
                callback: function(r) {
                    if (r.message) {
                        // Build detailed message for dialog
                        let message = '';
                        const results = r.message.results || [];
                        
                        if (results.length > 0) {
                            message = '<div class="table-responsive"><table class="table table-bordered">';
                            message += '<tr><th>Integration</th><th>Type</th><th>Status</th><th>Enabled</th><th>Message</th></tr>';
                            
                            results.forEach(result => {
                                const statusColor = result.status === 'success' ? 'green' : 'red';
                                const enabledStatus = result.enabled ? 
                                    '<span class="indicator green">Yes</span>' : 
                                    '<span class="indicator red">No</span>';
                                
                                message += `<tr>
                                    <td>${result.integration || ''}</td>
                                    <td>${result.integration_type || ''}</td>
                                    <td><span class="indicator ${statusColor}">${result.status}</span></td>
                                    <td>${enabledStatus}</td>
                                    <td>${result.message || ''}</td>
                                </tr>`;
                            });
                            
                            message += '</table></div>';
                        } else {
                            message = __('No results returned');
                        }
                        
                        // First refresh the form to update the UI
                        frm.refresh();
                        
                        // Use setTimeout to ensure the refresh has completed before showing dialog
                        setTimeout(() => {
                            frappe.msgprint({
                                title: __('Integration Test Results'),
                                indicator: r.message.status === 'success' ? 'green' : 'red',
                                message: message,
                                onhide: function() {
                                    // Refresh again after the dialog is closed to ensure
                                    // any changes are visible
                                    frm.reload_doc();
                                }
                            });
                        }, 300);
                    } else {
                        frappe.msgprint({
                            title: __('Test Failed'),
                            indicator: 'red',
                            message: __('No response from server')
                        });
                    }
                }
            });
        }, __('Integrations'));

        // Add button to test LLM OCR connection if LLM OCR is enabled
        if (frm.doc.ocr_enabled && frm.doc.ocr_engine === "llm_api") {
            frm.add_custom_button(__('Test LLM OCR Connection'), function() {
                frappe.call({
                    doc: frm.doc,
                    method: 'test_llm_ocr_connection',
                    freeze: true,
                    freeze_message: __('Testing LLM API connection...'),
                    callback: function(r) {
                        if (r.message) {
                            let message = r.message.message || '';
                            let success = r.message.success;
                            let model = r.message.model || 'Unknown';
                            let apiResponse = r.message.api_response || '';
                            
                            // Check if we have visual test results
                            let visualTestHtml = '';
                            if (r.message.visual_test) {
                                const visualSuccess = r.message.visual_test.success;
                                visualTestHtml = `
                                    <div class="mt-3">
                                        <h5>Visual OCR Test</h5>
                                        <div class="alert alert-${visualSuccess ? 'success' : 'warning'}">
                                            ${r.message.visual_test.message}
                                        </div>
                                    </div>
                                `;
                            }
                            
                            // Build detailed result HTML
                            const resultHtml = `
                                <div>
                                    <div class="mb-3">
                                        <strong>Model:</strong> ${model}
                                    </div>
                                    <div class="mb-3">
                                        <strong>Connection Status:</strong> 
                                        <span class="indicator ${success ? 'green' : 'red'}">
                                            ${success ? 'Connected' : 'Failed'}
                                        </span>
                                    </div>
                                    <div class="mb-3">
                                        <strong>Details:</strong> ${message}
                                    </div>
                                    ${visualTestHtml}
                                    ${apiResponse ? `
                                    <div class="mt-3">
                                        <h5>API Response Sample</h5>
                                        <pre class="bg-light p-2" style="max-height: 150px; overflow: auto;">${apiResponse}</pre>
                                    </div>
                                    ` : ''}
                                </div>
                            `;
                            
                            frappe.msgprint({
                                title: __('LLM OCR Connection Test'),
                                message: resultHtml,
                                indicator: success ? 'green' : 'red'
                            });
                        } else {
                            frappe.msgprint({
                                title: __('Test Failed'),
                                indicator: 'red',
                                message: __('No response from server')
                            });
                        }
                    }
                });
            }, __('OCR Settings'));
        }

        // Add button to delete old files
        if (frm.doc.delete_old_files && frm.doc.days_to_keep_files > 0) {
            frm.add_custom_button(__('Delete Old Files'), function() {
                frappe.confirm(
                    __(`This will permanently delete files from Doc2Sys Items older than ${frm.doc.days_to_keep_files} days. Continue?`),
                    function() {
                        frappe.call({
                            method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.delete_old_doc2sys_files',
                            args: {
                                user_settings: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Deleting old files...'),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    const details = r.message.details || {};
                                    const message = `
                                        <div>
                                            <p>${r.message.message}</p>
                                            ${details.items_processed ? `
                                            <div class="table-responsive">
                                                <table class="table table-bordered">
                                                    <tr><th>Items Processed</th><td>${details.items_processed}</td></tr>
                                                    <tr><th>Files Deleted</th><td>${details.files_deleted}</td></tr>
                                                    <tr><th>Files With Errors</th><td>${details.files_not_found}</td></tr>
                                                </table>
                                            </div>
                                            ` : ''}
                                        </div>
                                    `;
                                    
                                    frappe.msgprint({
                                        title: __('File Cleanup Complete'),
                                        message: message,
                                        indicator: 'green'
                                    });
                                } else {
                                    frappe.msgprint({
                                        title: __('File Cleanup Failed'),
                                        message: r.message ? r.message.message : __('Unknown error'),
                                        indicator: 'red'
                                    });
                                }
                            }
                        });
                    }
                );
            }, __('Tools'));
        }
    },
    
    ocr_enabled: function(frm) {
        // When OCR is enabled/disabled, refresh form to show/hide related fields
        frm.refresh();
    },

    ocr_engine: function(frm) {
        // When OCR engine changes, refresh form to show/hide related sections
        frm.refresh();
    },

    llm_provider: function(frm) {
        // When LLM provider changes, refresh form to show/hide sections
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

frappe.ui.form.on('Doc2Sys User Integration', {
    integration_type: function(frm, cdt, cdn) {
        // Reset field values when integration type changes
        let row = locals[cdt][cdn];
        
        frappe.model.set_value(cdt, cdn, 'api_key', '');
        frappe.model.set_value(cdt, cdn, 'api_secret', '');
        frappe.model.set_value(cdt, cdn, 'access_token', '');
        frappe.model.set_value(cdt, cdn, 'refresh_token', '');
        frappe.model.set_value(cdt, cdn, 'base_url', '');
        frappe.model.set_value(cdt, cdn, 'realm_id', '');
    },
    
    integration_name: function(frm, cdt, cdn) {
        // When adding a new integration, show reminder to test before it's enabled
        frappe.show_alert({
            message: __('Remember to test the integration to enable it'),
            indicator: 'blue'
        }, 5);
    }
});
