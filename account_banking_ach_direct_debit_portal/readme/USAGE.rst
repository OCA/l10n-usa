### Requirements

- A Plaid developer account
- Your `client_id` and `secret` from the Plaid dashboard

### Configuration in Odoo

To configure your Plaid credentials in Odoo:

1. Go to **Settings > Invoicing > Plaid**.
2. Update the following parameters:
   - **Plaid Environment**: Choose `Sandbox`, `Development`, or `Production`.
   - **Client ID**: Enter your Plaid `client_id`.
   - **Secret**: Enter your Plaid `secret`.

   Alternatively, you may use environment variables or a settings module if your Odoo deployment supports it.
