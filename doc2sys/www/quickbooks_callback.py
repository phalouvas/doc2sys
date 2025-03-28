import frappe
import requests
from frappe import _

def get_context(context):
    """Handle QuickBooks OAuth callback"""
    try:
        # Get the authorization code from URL parameters
        code = frappe.form_dict.get('code')
        realmId = frappe.form_dict.get('realmId')
        state = frappe.form_dict.get('state')
        
        if not (code and realmId and state):
            context.error = _("Missing required parameters")
            return
        
        # Get settings document from state parameter (should be the doc name)
        settings_doc = frappe.get_doc("Doc2Sys User Settings", state)
        
        # Exchange code for tokens
        client_id = settings_doc.client_id
        client_secret = frappe.utils.password.get_decrypted_password(
            "Doc2Sys User Settings", state, "client_secret"
        )
        
        # Determine if using sandbox
        is_sandbox = settings_doc.quickbooks_sandbox
        
        # Exchange auth code for tokens
        token_endpoint = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        
        # Your callback URL - must match what's registered in QuickBooks app
        redirect_uri = frappe.utils.get_url("/quickbooks_callback")
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        }
        
        token_response = requests.post(
            token_endpoint,
            data=token_data,
            auth=(client_id, client_secret)
        )
        
        if token_response.status_code != 200:
            context.error = _(f"Failed to get access tokens: {token_response.text}")
            return
        
        tokens = token_response.json()
        
        # Save tokens to settings
        frappe.db.set_value("Doc2Sys User Settings", state, {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "realm_id": realmId,
            "integration_enabled": 1
        })
        frappe.db.commit()
        
        context.success = _("Successfully authenticated with QuickBooks")
        
    except Exception as e:
        context.error = _(f"Error during QuickBooks authorization: {str(e)}")