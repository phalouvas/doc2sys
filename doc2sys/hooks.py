app_name = "doc2sys"
app_title = "Doc2Sys"
app_publisher = "KAINOTOMO PH LTD"
app_description = "A document automation software that extracts data from various files (images, PDFs etc), validates them, and integrates them into accounting systems, deployable both in the cloud and on-premises."
app_email = "info@kainotomo.com"
app_license = "gpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "doc2sys",
# 		"logo": "/assets/doc2sys/logo.png",
# 		"title": "Doc2Sys",
# 		"route": "/doc2sys",
# 		"has_permission": "doc2sys.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/doc2sys/css/doc2sys.css"
# app_include_js = "/assets/doc2sys/js/doc2sys.js"

# include js, css files in header of web template
# web_include_css = "/assets/doc2sys/css/doc2sys.css"
web_include_js = "/assets/doc2sys/js/doc2sys.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "doc2sys/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_list_js = {
    "Doc2Sys Item": "doctype/doc2sys_item/doc2sys_item_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "doc2sys/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "doc2sys.utils.jinja_methods",
# 	"filters": "doc2sys.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "doc2sys.install.before_install"
after_install = "doc2sys.setup.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "doc2sys.uninstall.before_uninstall"
# after_uninstall = "doc2sys.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "doc2sys.utils.before_app_install"
# after_app_install = "doc2sys.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "doc2sys.utils.before_app_uninstall"
# after_app_uninstall = "doc2sys.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "doc2sys.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# Doc Events
# doc_events = {
#    "Doc2Sys Item": {
#        "after_insert": "doc2sys.integrations.events.trigger_integrations_on_insert",
#        "on_update": "doc2sys.integrations.events.trigger_integrations_on_update",
#    }
#}

doc_events = {
    "Payment Entry": {
        "on_submit": "doc2sys.doc2sys.utils.payment_integration.update_user_credits"
    }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "cron": {
        # Monitor folders based on configured interval
        "*/15 * * * *": [
            "doc2sys.doc2sys.tasks.folder_monitor.monitor_folders"
        ]
    },
    "daily": [
        "doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings.delete_old_doc2sys_files"
    ]
}

# Testing
# -------

# before_tests = "doc2sys.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "doc2sys.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "doc2sys.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["doc2sys.utils.before_request"]
# after_request = ["doc2sys.utils.after_request"]

# Job Events
# ----------
# before_job = ["doc2sys.utils.before_job"]
# after_job = ["doc2sys.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"doc2sys.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
