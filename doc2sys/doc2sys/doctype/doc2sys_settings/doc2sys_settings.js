// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Doc2Sys Settings', {
    refresh: function(frm) {

        // Add test Ollama connection button
        if (frm.doc.use_llm && frm.doc.llm_provider === "Ollama") {
            frm.add_custom_button(__('Test Ollama Connection'), function() {
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_settings.doc2sys_settings.test_ollama_connection',
                    freeze: true,
                    freeze_message: __('Testing connection to Ollama server...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Ollama Connection Successful'),
                                message: r.message.message + "<br><br>" + 
                                         __('Available models: ') + r.message.available_models.join(', ') + "<br><br>" +
                                         __('Response sample: ') + `<pre>${r.message.response_sample}</pre>`,
                                indicator: 'green'
                            });
                        } else {
                            frappe.msgprint({
                                title: __('Ollama Connection Failed'),
                                message: r.message ? r.message.message : __('Unknown error'),
                                indicator: 'red'
                            });
                        }
                    }
                });
            }, __('LLM'));
        }
    }
});
