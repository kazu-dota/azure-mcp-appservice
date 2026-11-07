output "config" {
  value = {
    subscription_id         = var.subscription_id
    tenant_id               = var.tenant_id
    prefix                  = var.prefix
    location                = var.location
    app_location            = coalesce(var.app_location, var.location)
    expires_at              = var.expires_at
    resource_group_name     = azurerm_resource_group.workload.name
    bootstrap_group_name    = azurerm_resource_group.bootstrap.name
    state_account           = azurerm_storage_account.state.name
    deployer_client_id      = azurerm_user_assigned_identity.deployer.client_id
    deployer_object_id      = azurerm_user_assigned_identity.deployer.principal_id
    frontend_identity_id    = azurerm_user_assigned_identity.frontend.id
    frontend_client_id      = azurerm_user_assigned_identity.frontend.client_id
    frontend_object_id      = azurerm_user_assigned_identity.frontend.principal_id
    mcp_identity_id         = azurerm_user_assigned_identity.mcp.id
    mcp_client_id           = azurerm_user_assigned_identity.mcp.client_id
    mcp_object_id           = azurerm_user_assigned_identity.mcp.principal_id
    frontend_login_id       = azuread_application.frontend.client_id
    frontend_application_id = azuread_application.frontend.object_id
    mcp_audience            = azuread_application.mcp.client_id
    mcp_application_id      = azuread_application.mcp.object_id
    operator_object_id      = data.azuread_client_config.current.object_id
  }
}
