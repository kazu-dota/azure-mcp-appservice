data "azurerm_client_config" "current" {}
data "azuread_client_config" "current" {}
data "azuread_service_principal" "graph" {
  client_id = "00000003-0000-0000-c000-000000000000"
}

locals {
  tags           = { project = var.prefix, purpose = "azure-mcp-demo", expires_at = var.expires_at }
  owners         = [data.azuread_client_config.current.object_id, azurerm_user_assigned_identity.deployer.principal_id]
  invoke_role_id = uuidv5("dns", "azure-mcp-demo/Mcp.Invoke")
  login_role_id  = uuidv5("dns", "azure-mcp-demo/Frontend.User")
}

resource "azurerm_resource_group" "bootstrap" {
  name     = "${var.prefix}-bootstrap"
  location = var.location
  tags     = local.tags
}
resource "azurerm_resource_group" "workload" {
  name     = "${var.prefix}-workload"
  location = var.location
  tags     = local.tags
}

resource "azurerm_storage_account" "state" {
  name                            = "${var.prefix}state"
  resource_group_name             = azurerm_resource_group.bootstrap.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}
resource "azurerm_role_assignment" "state_operator" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}
resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
  depends_on            = [azurerm_role_assignment.state_operator]
}

resource "azurerm_user_assigned_identity" "deployer" {
  name                = "${var.prefix}-deployer"
  resource_group_name = azurerm_resource_group.bootstrap.name
  location            = var.location
  tags                = local.tags
}
resource "azurerm_federated_identity_credential" "github" {
  name                      = "github-main"
  user_assigned_identity_id = azurerm_user_assigned_identity.deployer.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = var.github_subject
}
resource "azurerm_user_assigned_identity" "frontend" {
  name                = "${var.prefix}-frontend"
  resource_group_name = azurerm_resource_group.bootstrap.name
  location            = var.location
  tags                = local.tags
}
resource "azurerm_user_assigned_identity" "mcp" {
  name                = "${var.prefix}-mcp"
  resource_group_name = azurerm_resource_group.bootstrap.name
  location            = var.location
  tags                = local.tags
}
resource "azurerm_role_assignment" "deployer_workload" {
  for_each             = toset(["Contributor", "Role Based Access Control Administrator"])
  scope                = azurerm_resource_group.workload.id
  role_definition_name = each.value
  principal_id         = azurerm_user_assigned_identity.deployer.principal_id
}
resource "azurerm_role_assignment" "deployer_bootstrap" {
  scope                = azurerm_resource_group.bootstrap.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.deployer.principal_id
}
resource "azurerm_role_assignment" "state_deployer" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.deployer.principal_id
}

resource "azuread_application" "frontend" {
  display_name     = "${var.prefix}-frontend"
  owners           = local.owners
  sign_in_audience = "AzureADMyOrg"
  # Easy Auth requests code + id_token; the workload stack owns only redirect URIs.
  lifecycle { ignore_changes = [web[0].redirect_uris] }
  web {
    implicit_grant {
      id_token_issuance_enabled     = true
      access_token_issuance_enabled = false
    }
  }
  app_role {
    id                   = local.login_role_id
    allowed_member_types = ["User"]
    description          = "Sign in to this demonstration"
    display_name         = "Demo user"
    value                = "Frontend.User"
  }
}
resource "azuread_service_principal" "frontend" {
  client_id                    = azuread_application.frontend.client_id
  owners                       = local.owners
  app_role_assignment_required = true
}
resource "azuread_app_role_assignment" "operator" {
  app_role_id         = local.login_role_id
  principal_object_id = data.azuread_client_config.current.object_id
  resource_object_id  = azuread_service_principal.frontend.object_id
}
resource "azuread_application_federated_identity_credential" "frontend" {
  application_id = azuread_application.frontend.id
  display_name   = "easy-auth-managed-identity"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
  subject        = azurerm_user_assigned_identity.frontend.principal_id
}

resource "azuread_application" "mcp" {
  display_name     = "${var.prefix}-mcp"
  owners           = local.owners
  sign_in_audience = "AzureADMyOrg"
  # The dedicated identifier_uri resource owns this collection.
  lifecycle { ignore_changes = [identifier_uris] }
  api { requested_access_token_version = 2 }
  app_role {
    id                   = local.invoke_role_id
    allowed_member_types = ["Application"]
    description          = "Invoke read-only inventory tools"
    display_name         = "Invoke MCP"
    value                = "Mcp.Invoke"
  }
}
resource "azuread_application_identifier_uri" "mcp" {
  application_id = azuread_application.mcp.id
  identifier_uri = "api://${azuread_application.mcp.client_id}"
}
resource "azuread_service_principal" "mcp" {
  client_id                    = azuread_application.mcp.client_id
  owners                       = local.owners
  app_role_assignment_required = true
  depends_on                   = [azuread_application_identifier_uri.mcp]
}
resource "azuread_app_role_assignment" "invoke" {
  app_role_id         = local.invoke_role_id
  principal_object_id = azurerm_user_assigned_identity.frontend.principal_id
  resource_object_id  = azuread_service_principal.mcp.object_id
}

# Cleanup can delete only the Entra applications it owns, without tenant-wide application rights.
resource "azuread_app_role_assignment" "cleanup_owned_apps" {
  app_role_id         = data.azuread_service_principal.graph.app_role_ids["Application.ReadWrite.OwnedBy"]
  principal_object_id = azurerm_user_assigned_identity.deployer.principal_id
  resource_object_id  = data.azuread_service_principal.graph.object_id
}
