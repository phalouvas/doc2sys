frappe.ready(function () {
    // Only run on the list view
    if (frappe.web_form_list) {
        // Add the upload button and credits container to the list view
        $('.web-list-header').append(`
            <div class="d-flex align-items-center">
                <button class="btn btn-primary btn-sm btn-upload-document">
                    ${__('Upload')}
                </button>
                <span class="user-credits ml-2 text-danger text-center"></span>
            </div>
        `);

        // Get and display user credits
        frappe.call({
            method: "doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.get_user_credits",
            callback: function(response) {
                if (response.message && response.message.success) {
                    // Format and display credits
                    const credits = response.message.credits || 0;
                    // Use Frappe's currency formatter
                    $('.user-credits').html(`${__('Credits')}:<br/> ${format_currency(credits, "EUR")}`);
                }
            }
        });

        // Handle click event for the upload button
        $('.btn-upload-document').on('click', function () {
            // Get the current user
            const current_user = frappe.session.user;
            // Construct the folder path
            const folder_path = `Home/Doc2Sys/${current_user}`;

            // Use Frappe's built-in file uploader
            new frappe.ui.FileUploader({
                as_dataurl: false,
                allow_multiple: true,
                folder: folder_path,
                on_success: function (file_doc) {
                    // Create doc2sys_items after successful upload
                    create_doc2sys_items_from_files(file_doc);
                }
            });
        });

        // Hide the "Create a new Doc2Sys Item" button on document list view
        setTimeout(function () {
            // Hide the default "New" button 
            $('.no-result').hide();
        }, 500);
    }
});

// Function to process the uploaded files and create doc2sys_items
function create_doc2sys_items_from_files(file_docs) {
    if (!Array.isArray(file_docs)) {
        file_docs = [file_docs]; // Convert to array if single file
    }

    if (file_docs.length === 0) return;

    const total = file_docs.length;
    let processed = 0;

    // Show progress dialog
    const dialog = new frappe.ui.Dialog({
        title: __('Creating Documents'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'progress_area',
                options: `<div class="progress">
                    <div class="progress-bar" style="width: 0%"></div>
                </div>
                <p class="text-muted" style="margin-top: 10px">
                    <span class="processed">0</span> ${__('of')} ${total} ${__('documents created')}
                </p>`
            }
        ]
    });

    dialog.show();

    // Process files one by one to create doc2sys_items
    function process_next_file(index) {
        if (index >= file_docs.length) {
            // All files processed
            setTimeout(() => {
                dialog.hide();
                frappe.show_alert({
                    message: __(`Created ${processed} documents successfully`),
                    indicator: 'green'
                });
                // Refresh the web form list
                frappe.web_form_list.refresh();
            }, 1000);
            return;
        }

        const file_doc = file_docs[index];

        // Create doc2sys_item from file
        frappe.call({
            method: 'doc2sys.doc2sys.doctype.doc2sys_item.doc2sys_item.create_item_from_file',
            args: {
                file_doc_name: file_doc.name
            },
            callback: function (r) {
                processed++;

                // Update progress
                const percent = (processed / total) * 100;
                dialog.$wrapper.find('.progress-bar').css('width', percent + '%');
                dialog.$wrapper.find('.processed').text(processed);

                // Process next file
                process_next_file(index + 1);
            }
        });
    }

    // Start processing files
    process_next_file(0);
}