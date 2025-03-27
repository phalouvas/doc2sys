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
            
            // Add QuickBooks authorization button container
            const qbButtonContainer = $(`
                <div id="quickbooks-auth-container" class="frappe-control" style="margin-top: 10px; display: none;">
                    <button id="connect-quickbooks-button" class="btn btn-primary">
                        ${__('Connect to QuickBooks')}
                    </button>
                    <div id="quickbooks-auth-result" class="alert mt-3" style="display: none;"></div>
                </div>
            `);
            
            // Append the button containers
            integrationSection.append(buttonContainer);
            integrationSection.append(qbButtonContainer);
            
            // Add click handler for test button
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
            
            // Add click handler for QuickBooks connect button
            $('#connect-quickbooks-button').click(function(e) {
                e.preventDefault();
                
                // Update button state and show loading
                const $button = $(this);
                $button.prop('disabled', true);
                $button.html(`<i class="fa fa-spinner fa-spin"></i> ${__('Connecting...')}`);
                
                // Hide previous results
                $('#quickbooks-auth-result').hide();
                
                // Get current values from the form
                const current_values = frappe.web_form.get_values();
                
                // Call the QuickBooks auth URL method
                frappe.call({
                    method: 'doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.get_quickbooks_auth_url',
                    args: {
                        user_settings: current_values.name
                    },
                    callback: function(r) {
                        // Reset button state
                        $button.prop('disabled', false);
                        $button.html(__('Connect to QuickBooks'));
                        
                        if (r.message && r.message.success) {
                            // Open the authorization URL in a new window
                            const authWindow = window.open(r.message.url, 'QuickBooksAuth', 
                                'width=600,height=700,scrollbars=yes,resizable=yes');
                            
                            // Show instructions
                            const $result = $('#quickbooks-auth-result');
                            $result.removeClass('alert-danger').addClass('alert-info');
                            $result.html(`<i class="fa fa-info-circle"></i> ${__('Please complete the authorization in the new window. This page will refresh when complete.')}`);
                            $result.show();
                            
                            // Set up a timer to check if authentication is complete
                            const checkAuthInterval = setInterval(function() {
                                if (authWindow.closed) {
                                    clearInterval(checkAuthInterval);
                                    
                                    // Refresh the page to reflect new auth status
                                    window.location.reload();
                                }
                            }, 500);
                        } else {
                            // Show error message
                            const $result = $('#quickbooks-auth-result');
                            $result.removeClass('alert-info').addClass('alert-danger');
                            $result.html(`<i class="fa fa-times-circle"></i> ${__('Error')}: ${r.message ? r.message.message : 'Failed to get authorization URL'}`);
                            $result.show();
                        }
                    },
                    error: function(err) {
                        // Reset button state
                        $button.prop('disabled', false);
                        $button.html(__('Connect to QuickBooks'));
                        
                        // Show error message
                        const $result = $('#quickbooks-auth-result');
                        $result.removeClass('alert-info').addClass('alert-danger');
                        $result.html(`<i class="fa fa-times-circle"></i> ${__('Error')}: ${err.message || 'Unknown error occurred'}`);
                        $result.show();
                    }
                });
            });
            
            // Show/hide QuickBooks button based on integration type
            function toggleQuickBooksButton() {
                const current_values = frappe.web_form.get_values();
                
                // Only show the button if QuickBooks is selected and credentials are filled
                if (current_values.integration_type === 'QuickBooks' && 
                    current_values.client_id && 
                    current_values.client_secret) {
                    $('#quickbooks-auth-container').show();
                } else {
                    $('#quickbooks-auth-container').hide();
                }
            }
            
            // Call once on initial load
            toggleQuickBooksButton();
            
            // Listen for changes to the integration type and credentials fields
            $('[data-fieldname="integration_type"], [data-fieldname="client_id"], [data-fieldname="client_secret"]')
                .on('change', toggleQuickBooksButton);
        } else {
            console.log('Integration section not found');
        }
    }
});