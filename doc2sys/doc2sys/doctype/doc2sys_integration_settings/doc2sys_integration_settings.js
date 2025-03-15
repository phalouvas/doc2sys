frappe.ui.form.on('Doc2Sys Integration Settings', {
    refresh: function(frm) {
        // Add button to test connection
        frm.add_custom_button(__('Test Connection'), function() {
            frappe.show_alert({
                message: __('Testing connection...'),
                indicator: 'blue'
            });
            
            frm.call({
                method: 'test_connection',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message && r.message.status === 'success') {
                        frappe.show_alert({
                            message: __('Connection successful: ') + r.message.message,
                            indicator: 'green'
                        });
                    } else {
                        frappe.show_alert({
                            message: __('Connection failed: ') + (r.message.message || 'Unknown error'),
                            indicator: 'red'
                        });
                    }
                }
            });
        });
        
        // Add button to get field mapping suggestions
        frm.add_custom_button(__('Get Mapping Fields'), function() {
            frm.call({
                method: 'get_mapping_fields',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message && r.message.length) {
                        let fields = r.message;
                        let mapping = {};
                        
                        fields.forEach(function(field) {
                            mapping[field.field] = '';
                        });
                        
                        // Update the field_mapping field with the template
                        frm.set_value('field_mapping', JSON.stringify(mapping, null, 2));
                        frappe.show_alert({
                            message: __('Field mapping template generated'),
                            indicator: 'green'
                        });
                    } else {
                        frappe.show_alert({
                            message: __('No fields found or error occurred'),
                            indicator: 'red'
                        });
                    }
                }
            });
        });
    },
    
    integration_type: function(frm) {
        // Reset field values when integration type changes
        frm.set_value('api_key', '');
        frm.set_value('api_secret', '');
        frm.set_value('access_token', '');
        frm.set_value('refresh_token', '');
        frm.set_value('base_url', '');
        frm.set_value('realm_id', '');
        frm.set_value('field_mapping', '');
    }
});