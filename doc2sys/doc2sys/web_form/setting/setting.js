frappe.ready(function() {
    // Try multiple approaches to add the button
    
    // Approach 1: Use setTimeout to ensure DOM is ready
    setTimeout(addTestButton, 1000);
    
    // Approach 2: Use mutation observer to detect when fields are added
    setupMutationObserver();
    
    // Approach 3: Keep the after_load hook as a fallback
    frappe.web_form.after_load = function() {
        console.log('after_load triggered');
        addTestButton();
    };
    
    function setupMutationObserver() {
        // Create an observer to watch for DOM changes
        const observer = new MutationObserver(function(mutations) {
            if ($('[data-fieldname="integration_type"]').length > 0) {
                addTestButton();
                observer.disconnect(); // Stop observing once button is added
            }
        });
        
        // Start observing the form container
        const formContainer = document.querySelector('.web-form-container');
        if (formContainer) {
            observer.observe(formContainer, { childList: true, subtree: true });
        }
    }
    
    function addTestButton() {
        // Check if button already exists to prevent duplicates
        if (document.getElementById('integration-test-container')) {
            return;
        }

		if (frappe.web_form.in_edit_mode) {
			return
		}
        
        // Find the integration section
        const integrationSection = $('[data-fieldname="integration_type"]').closest('div.section-body');
        
        if (integrationSection.length) {
            // Create container for the button
            const buttonContainer = $(`
                <div id="integration-test-container" class="frappe-control" style="margin-top: 20px;">
                    <button id="test-integration-button" class="btn btn-primary">
                        ${__('Test Integration')}
                    </button>
                    <div id="integration-test-result" class="alert mt-3" style="display: none;"></div>
                </div>
            `);
            
            // Append the button container
            integrationSection.append(buttonContainer);
            
            // Add click handler
            $('#test-integration-button').click(function(e) {
                e.preventDefault();
                
                // Update button state and show loading
                const $button = $(this);
                $button.prop('disabled', true);
                $button.html(`<i class="fa fa-spinner fa-spin"></i> ${__('Testing...')}`);
                
                // Hide previous results
                $('#integration-test-result').hide();
                
                // Get current values from the form
                const current_values = frappe.web_form.get_values();
                
                // Call the test integration method
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.test_integration_user',
                    args: {
                        user: current_values.user
                    },
                    callback: function(r) {
                        // Reset button state
                        $button.prop('disabled', false);
                        $button.html(__('Test Integration'));
                        
                        const $result = $('#integration-test-result');
                        
                        if (r.message) {
                            
                            if (r.message.status === 'success') {
                                $result.removeClass('alert-danger').addClass('alert-success');
                                $result.html(`<i class="fa fa-check-circle"></i> ${__('Success')}: ${r.message.message}`);
                            } else {
                                $result.removeClass('alert-success').addClass('alert-danger');
                                $result.html(`<i class="fa fa-times-circle"></i> ${__('Error')}: ${r.message.message}`);
                            }
                            $result.show();
                        }
                    },
                    error: function(err) {
                        console.error('Integration test error:', err);
                        
                        // Reset button state
                        $button.prop('disabled', false);
                        $button.html(__('Test Integration'));
                        
                        // Show error message
                        const $result = $('#integration-test-result');
                        $result.removeClass('alert-success').addClass('alert-danger');
                        $result.html(`<i class="fa fa-times-circle"></i> ${__('Error')}: ${err.message || 'Unknown error occurred'}`);
                        $result.show();
                    }
                });
            });
            
        } else {
            console.log('Integration section not found');
        }
    }
});