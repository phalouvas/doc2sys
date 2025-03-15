frappe.ui.form.on('Doc2Sys Integration Log', {
    refresh: function(frm) {
        // Add button to retry failed integrations
        if (frm.doc.status === 'error') {
            frm.add_custom_button(__('Retry Integration'), function() {
                frappe.confirm(
                    __('Are you sure you want to retry this integration?'),
                    function() {
                        frm.call({
                            method: 'retry_integration',
                            doc: frm.doc,
                            callback: function(r) {
                                if (r.message && r.message.status === 'success') {
                                    frappe.show_alert({
                                        message: __('Integration retried successfully'),
                                        indicator: 'green'
                                    });
                                    frm.reload_doc();
                                } else {
                                    frappe.show_alert({
                                        message: __('Retry failed: ') + (r.message.message || 'Unknown error'),
                                        indicator: 'red'
                                    });
                                }
                            }
                        });
                    }
                );
            });
        }
    }
});