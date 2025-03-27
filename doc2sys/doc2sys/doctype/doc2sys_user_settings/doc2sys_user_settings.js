// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys User Settings', {
    refresh: function (frm) {

        // Add manual folder processing button
        if (frm.doc.monitoring_enabled) {
            frm.add_custom_button(__('Process Folder Now'), function () {
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.process_user_folder',
                    args: {
                        user_settings: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Processing files from monitor folder...'),
                    callback: function (r) {
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

        // Update the Test Integration button click handler
        frm.add_custom_button(__('Test Integration'), function () {
            // Show a loading indicator
            frappe.show_alert({
                message: __('Testing integration...'),
                indicator: 'blue'
            });

            // Call server-side method to test the integration
            frappe.call({
                method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.test_integration',
                args: {
                    user_settings: frm.doc.name  // Changed from doc_name to user_settings
                },
                callback: function (r) {
                    if (r.message) {
                        if (r.message.status === 'success') {  // Changed from r.message.success to match Python return value
                            frappe.show_alert({
                                message: __('Integration test successful: ') + r.message.message,
                                indicator: 'green'
                            });
                        } else {
                            frappe.show_alert({
                                message: __('Integration test failed: ') + r.message.message,
                                indicator: 'red'
                            });
                        }
                    }
                }
            });
        }, __('Integration'));

        // Add button to delete old files
        if (frm.doc.delete_old_files && frm.doc.days_to_keep_files > 0) {
            frm.add_custom_button(__('Delete Old Files'), function () {
                frappe.confirm(
                    __(`This will permanently delete files from Doc2Sys Items older than ${frm.doc.days_to_keep_files} days. Continue?`),
                    function () {
                        frappe.call({
                            method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.delete_old_doc2sys_files',
                            args: {
                                user_settings: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Deleting old files...'),
                            callback: function (r) {
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
