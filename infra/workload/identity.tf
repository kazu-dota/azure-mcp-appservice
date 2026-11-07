# Bootstrap grants write access to owned applications only.
resource "azuread_application_redirect_uris" "frontend" {
  application_id = "/applications/${var.config.frontend_application_id}"
  type           = "Web"
  redirect_uris  = ["https://${azurerm_linux_web_app.frontend.default_hostname}/.auth/login/aad/callback"]
}
