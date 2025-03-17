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
        
    },
    
    integration_type: function(frm) {
        // Reset field values when integration type changes
        frm.set_value('api_key', '');
        frm.set_value('api_secret', '');
        frm.set_value('access_token', '');
        frm.set_value('refresh_token', '');
        frm.set_value('base_url', '');
        frm.set_value('realm_id', '');
    }
});