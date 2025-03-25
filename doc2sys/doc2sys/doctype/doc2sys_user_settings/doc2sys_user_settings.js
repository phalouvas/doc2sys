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
