output "frontend_url" { value = "https://${azurerm_linux_web_app.frontend.default_hostname}" }
output "mcp_url" { value = "https://${azurerm_linux_web_app.mcp.default_hostname}/mcp" }
output "registry_name" { value = azurerm_container_registry.main.name }
output "registry_server" { value = azurerm_container_registry.main.login_server }
output "foundry_name" { value = azurerm_cognitive_account.foundry.name }
output "foundry_endpoint" { value = "https://${local.ai_hostname}" }
