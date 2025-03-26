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
            
            // Add Extract Data button
            if(frm.doc.status === 'Uploaded') {
                frm.add_custom_button(__('Extract Data'), function() {
                    // Show full screen processing overlay
                    frappe.dom.freeze(__('Extracting data from document...'));
                    
                    frm.call({
                        doc: frm.doc,
                        method: 'extract_data',
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
            }

            // Add trigger integrations button that actually processes the integrations
            if(frm.doc.status === 'Processed') {
                frm.add_custom_button(__('Trigger Integrations'), function() {
                    // Show full screen processing overlay
                    frappe.dom.freeze(__('Running integrations...'));
                    
                    frm.call({
                        doc: frm.doc,
                        method: 'trigger_integrations',
                        callback: function(r) {
                            // Unfreeze UI when processing is complete
                            frappe.dom.unfreeze();
                            
                            if(r.message) {
                                frappe.show_alert({
                                    message: __('Integrations completed'),
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

            // Add Process All Steps button at the end of Actions dropdown
            if(frm.doc.status === 'Uploaded') {
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
            }
            
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
