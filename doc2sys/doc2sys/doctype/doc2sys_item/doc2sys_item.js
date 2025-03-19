// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Item', {
    refresh: function(frm) {
        // Add custom buttons or functionality here
        // Add Reprocess button if a document is attached
        if(frm.doc.single_file) {
            // Add Extract Text Only button
            frm.add_custom_button(__('Extract Text Only'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Extracting text from document...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'extract_text_only',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Text extraction completed'),
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

        // Add Trigger Integrations button
        frm.add_custom_button(__('Trigger Integrations'), function() {
            frappe.call({
                method: 'doc2sys.integrations.events.trigger_integrations_on_update',
                args: {
                    doc: frm.doc
                },
                callback: function(r) {
                    if(r.message) {
                        frappe.show_alert({
                            message: __('Integrations triggered successfully'),
                            indicator: 'green'
                        }, 3);
                    }
                }
            });
        }, __('Actions'));

        // Update integration status
        update_integration_status(frm);
        
        // Add manual sync button
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__('Sync Integrations'), function() {
                frappe.call({
                    method: "doc2sys.integrations.events.trigger_integrations_on_update",
                    args: {
                        doc: frm.doc
                    },
                    callback: function(r) {
                        frappe.show_alert({message: __('Sync initiated'), indicator: 'green'});
                        setTimeout(function() {
                            update_integration_status(frm);
                        }, 3000); // Wait 3 seconds for processing
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
    
    onload: function(frm) {
        // Set the user to current user if creating a new document and user is not set
        if(frm.doc.__islocal && (!frm.doc.user || frm.doc.user === "")) {
            frm.set_value('user', frappe.session.user);
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

function update_integration_status(frm) {
    if (!frm.doc.name || frm.doc.__islocal) {
        return;
    }
    
    frm.call('get_integration_status')
        .then(r => {
            if (r.message) {
                render_integration_status(frm, r.message);
            }
        });
}

function render_integration_status(frm, statuses) {
    let html = '';
    
    if (statuses.length === 0) {
        html = '<div class="text-muted">No integrations have been processed</div>';
    } else {
        html = '<div class="integration-status-container">';
        
        statuses.forEach(status => {
            let indicator_class = 'gray';
            let status_text = 'Pending';
            
            if (status.status === 'success') {
                indicator_class = 'green';
                status_text = 'Success';
            } else if (status.status === 'error') {
                indicator_class = 'red';
                status_text = 'Failed';
            } else if (status.status === 'warning') {
                indicator_class = 'orange';
                status_text = 'Warning';
            }
            
            const timestamp = status.timestamp ? frappe.datetime.prettyDate(status.timestamp) : 'Never';
            
            html += `
                <div class="integration-status-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="indicator ${indicator_class}">
                            ${status.integration_type}
                        </span>
                        <span class="status-badge ${indicator_class}">${status_text}</span>
                    </div>
                    <div class="small text-muted mt-1">Last sync: ${timestamp}</div>
                    <div class="small mt-1 integration-message">${status.message || ''}</div>`;
                    
            // Add retry button for failed integrations
            if (status.status === 'error' && status.log_name) {
                html += `
                    <button class="btn btn-xs btn-default mt-2 retry-integration" 
                            data-log="${status.log_name}">
                        Retry
                    </button>`;
            }
            
            html += `</div>`;
        });
        
        html += '</div>';
    }
    
    $(frm.fields_dict.integration_status_html.wrapper).html(html);
    
    // Add custom styling
    frm.fields_dict.integration_status_html.$wrapper.find('.integration-status-container').css({
        'display': 'flex',
        'flex-direction': 'column',
        'gap': '10px'
    });
    
    frm.fields_dict.integration_status_html.$wrapper.find('.integration-status-item').css({
        'padding': '10px',
        'border-radius': '4px',
        'background-color': 'var(--control-bg)',
        'margin-bottom': '5px'
    });
    
    frm.fields_dict.integration_status_html.$wrapper.find('.status-badge').css({
        'padding': '2px 8px',
        'border-radius': '10px',
        'font-size': '11px',
        'font-weight': 'bold',
        'color': '#fff'
    });
    
    frm.fields_dict.integration_status_html.$wrapper.find('.status-badge.green').css('background-color', 'var(--green)');
    frm.fields_dict.integration_status_html.$wrapper.find('.status-badge.red').css('background-color', 'var(--red)');
    frm.fields_dict.integration_status_html.$wrapper.find('.status-badge.orange').css('background-color', 'var(--orange)');
    frm.fields_dict.integration_status_html.$wrapper.find('.status-badge.gray').css('background-color', 'var(--gray-600)');
    
    frm.fields_dict.integration_status_html.$wrapper.find('.integration-message').css({
        'max-height': '60px',
        'overflow-y': 'auto'
    });
    
    // Add retry functionality
    frm.fields_dict.integration_status_html.$wrapper.find('.retry-integration').on('click', function() {
        const log_name = $(this).data('log');
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Doc2Sys Integration Log",
                name: log_name
            },
            callback: function(r) {
                if (r.message) {
                    const log = r.message;
                    frappe.call({
                        method: "doc2sys.doc2sys.doctype.doc2sys_integration_log.doc2sys_integration_log.retry_integration",
                        args: {
                            log_name: log_name
                        },
                        callback: function(result) {
                            if (result.message && result.message.status === 'success') {
                                frappe.show_alert({message: 'Integration retried successfully', indicator: 'green'});
                                setTimeout(function() {
                                    update_integration_status(frm);
                                }, 2000);
                            } else {
                                frappe.show_alert({
                                    message: result.message?.message || 'Failed to retry integration', 
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                }
            }
        });
    });
}
