// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Item', {
    refresh: function(frm) {
        // Show the Upload File button only when document is NOT new and single_file is empty
        if (!frm.is_new() && (!frm.doc.single_file || frm.doc.single_file === "")) {
            // Get the username from the user field
            let username = frm.doc.user;
            
            // Create folder path using the username
            let folder = `Home/Doc2Sys/${username}`;
            
            // Add the button
            frm.add_custom_button(__('Upload File'), function() {
                new frappe.ui.FileUploader({
                    doctype: frm.doctype,
                    docname: frm.docname,
                    folder: folder,
                    on_success: function(file_doc) {
                        // Update the single_file field with the uploaded file URL
                        frm.set_value('single_file', file_doc.file_url);
                        frm.save();
                        
                        // If auto-process is enabled, trigger processing
                        if (frm.doc.auto_process_file) {
                            frappe.show_alert({
                                message: __('Processing file...'),
                                indicator: 'blue'
                            });
                            // Call your processing method here if needed
                        }
                        
                        frappe.show_alert({
                            message: __('File {0} uploaded successfully', [file_doc.file_name]),
                            indicator: 'green'
                        });
                    }
                });
            }).addClass("btn-primary");
        }

        // Get the username from the user field
        let username = frm.doc.user;
        
        // Create folder path using the username
        let folder = `Home/Doc2Sys/${username}`;
        
        // Add custom buttons or functionality here
        // Add buttons if a document is attached
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
            
            // Add Classify Document button
            frm.add_custom_button(__('Classify Document'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Classifying document...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'classify_document_only',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Document classification completed'),
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
            
            // Add Extract Data button
            frm.add_custom_button(__('Extract Data'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Extracting data from document...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'extract_data_only',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Data extraction completed'),
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

            // Add Extract Data button
            frm.add_custom_button(__('Extract Data From Azure'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Extracting data from document...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'extract_data_azure',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Data extraction completed'),
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
            
            // Add a separator in the Actions dropdown
            frm.add_custom_button('', function(){
                // No-op function 
            }, __('Actions')).addClass('dropdown-divider-btn disabled');
            
            // Add Process All Steps button at the end of Actions dropdown
            frm.add_custom_button(__('Process All Steps'), function() {
                // Show full screen processing overlay
                frappe.dom.freeze(__('Processing document with all steps...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'process_all',
                    callback: function(r) {
                        // Unfreeze UI when processing is complete
                        frappe.dom.unfreeze();
                        
                        if(r.message) {
                            frappe.show_alert({
                                message: __('Document processing completed'),
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
            
            // Add Reset Usage Metrics button
            frm.add_custom_button(__('Reset Usage Metrics'), function() {
                frappe.confirm(
                    __('This will reset all token usage and duration metrics to zero. Continue?'),
                    function() {
                        // Action if user says Yes
                        frappe.dom.freeze(__('Resetting metrics...'));
                        
                        frm.call({
                            doc: frm.doc,
                            method: 'reset_usage_metrics',
                            callback: function(r) {
                                frappe.dom.unfreeze();
                                
                                if(r.message) {
                                    frappe.show_alert({
                                        message: __('Usage metrics reset successfully'),
                                        indicator: 'green'
                                    }, 3);
                                    frm.refresh();
                                }
                            },
                            error: function() {
                                frappe.dom.unfreeze();
                            }
                        });
                    }
                );
            }, __('Actions'));
            
            // Add custom styling for the divider
            setTimeout(() => {
                $('.dropdown-divider-btn').css({
                    'pointer-events': 'none',
                    'color': '#ccc',
                    'border-bottom': '1px solid #eee',
                    'margin-bottom': '5px',
                    'padding-bottom': '5px'
                });
            }, 100);
        }

        // Update integration status on page load
        update_integration_status(frm);
        
        if (!frm.doc.__islocal) {
            // Add status refresh button that doesn't trigger integrations
            frm.add_custom_button(__('Refresh Status'), function() {
                update_integration_status(frm);
                frappe.show_alert({message: __('Integration status refreshed'), indicator: 'blue'});
            }, __('Integrations'));
            
            // Add trigger integrations button that actually processes the integrations
            frm.add_custom_button(__('Trigger Integrations'), function() {
                frappe.call({
                    method: "doc2sys.integrations.events.trigger_integrations_on_update",
                    args: {
                        doc: frm.doc
                    },
                    callback: function(r) {
                        frappe.show_alert({message: __('Integrations triggered'), indicator: 'green'});
                        setTimeout(function() {
                            update_integration_status(frm);
                        }, 3000); // Wait 3 seconds for processing
                    }
                });
            }, __('Integrations'));
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
    
    // Show loading indicator
    $(frm.fields_dict.integration_status_html.wrapper).html(
        '<div class="text-muted">Loading integration status...</div>'
    );
    
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
