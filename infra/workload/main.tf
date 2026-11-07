data "azurerm_resource_group" "workload" { name = var.config.resource_group_name }

locals {
  app_location = coalesce(var.config.app_location, var.config.location)
  prefix       = var.config.prefix
  tags         = { project = local.prefix, purpose = "azure-mcp-demo", expires_at = var.config.expires_at }
  issuer       = "https://login.microsoftonline.com/${var.config.tenant_id}/v2.0"
  mcp_hostname = azurerm_linux_web_app.mcp.default_hostname
  ai_hostname  = "${azurerm_cognitive_account.foundry.custom_subdomain_name}.openai.azure.com"
}

resource "azurerm_virtual_network" "main" {
  name                = "${local.prefix}-vnet"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = local.app_location
  address_space       = ["10.42.0.0/16"]
  tags                = local.tags
}
resource "azurerm_subnet" "integration" {
  name                 = "app-integration"
  resource_group_name  = data.azurerm_resource_group.workload.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.42.1.0/26"]
  delegation {
    name = "app-service"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}
resource "azurerm_subnet" "endpoints" {
  name                 = "private-endpoints"
  resource_group_name  = data.azurerm_resource_group.workload.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.42.2.0/24"]
}
resource "azurerm_network_security_group" "integration" {
  name                = "${local.prefix}-integration-nsg"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = local.app_location
  tags                = local.tags
}
resource "azurerm_subnet_network_security_group_association" "integration" {
  subnet_id                 = azurerm_subnet.integration.id
  network_security_group_id = azurerm_network_security_group.integration.id
}
resource "azurerm_private_dns_zone" "main" {
  for_each            = toset(["privatelink.azurewebsites.net", "privatelink.openai.azure.com", "privatelink.services.ai.azure.com", "privatelink.cognitiveservices.azure.com"])
  name                = each.value
  resource_group_name = data.azurerm_resource_group.workload.name
  tags                = local.tags
}
resource "azurerm_private_dns_zone_virtual_network_link" "main" {
  for_each             = azurerm_private_dns_zone.main
  name                 = "workload-vnet"
  private_dns_zone_id  = each.value.id
  virtual_network_id   = azurerm_virtual_network.main.id
  registration_enabled = false
  tags                 = local.tags
}

resource "azurerm_container_registry" "main" {
  name                = "${local.prefix}acr"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = var.config.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}
resource "azurerm_role_assignment" "acr_pull" {
  for_each             = { frontend = var.config.frontend_object_id, mcp = var.config.mcp_object_id }
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = each.value
}
resource "azurerm_role_assignment" "acr_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = var.config.deployer_object_id
}

resource "azurerm_cognitive_account" "foundry" {
  name                       = "${local.prefix}-foundry"
  resource_group_name        = data.azurerm_resource_group.workload.name
  location                   = var.config.location
  kind                       = "AIServices"
  sku_name                   = "S0"
  custom_subdomain_name      = "${local.prefix}-foundry"
  project_management_enabled = true
  identity { type = "SystemAssigned" }
  public_network_access_enabled = false
  local_auth_enabled            = false
  tags                          = local.tags
}
resource "azurerm_cognitive_deployment" "model" {
  name                 = var.model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }
  sku {
    name     = "Standard"
    capacity = 10
  }
  version_upgrade_option = "NoAutoUpgrade"
}
resource "azurerm_role_assignment" "inference" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.config.frontend_object_id
}
resource "azurerm_private_endpoint" "foundry" {
  name                = "${local.prefix}-foundry-pe"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = local.app_location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "foundry"
    private_connection_resource_id = azurerm_cognitive_account.foundry.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "foundry"
    private_dns_zone_ids = [for name, zone in azurerm_private_dns_zone.main : zone.id if name != "privatelink.azurewebsites.net"]
  }
  tags = local.tags
}

resource "azurerm_service_plan" "main" {
  name                = "${local.prefix}-plan"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = local.app_location
  os_type             = "Linux"
  sku_name            = "B1"
  worker_count        = 1
  tags                = local.tags
}

resource "azurerm_linux_web_app" "mcp" {
  name                                           = "${local.prefix}-mcp"
  resource_group_name                            = data.azurerm_resource_group.workload.name
  location                                       = local.app_location
  service_plan_id                                = azurerm_service_plan.main.id
  https_only                                     = true
  public_network_access_enabled                  = false
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  identity {
    type         = "UserAssigned"
    identity_ids = [var.config.mcp_identity_id]
  }
  site_config {
    always_on                                     = true
    ftps_state                                    = "Disabled"
    minimum_tls_version                           = "1.2"
    health_check_path                             = "/health"
    container_registry_use_managed_identity       = true
    container_registry_managed_identity_client_id = var.config.mcp_client_id
    application_stack {
      docker_registry_url = "https://${azurerm_container_registry.main.login_server}"
      docker_image_name   = "demo:${var.image_tag}"
    }
  }
  app_settings = {
    APP_MODULE                          = "app.mcp_server:create_app"
    APP_ENV                             = "production"
    WEBSITES_PORT                       = "8000"
    AZURE_TENANT_ID                     = var.config.tenant_id
    MCP_HOSTNAME                        = "${local.prefix}-mcp.azurewebsites.net"
    MCP_AUDIENCE                        = var.config.mcp_audience
    FRONTEND_CLIENT_ID                  = var.config.frontend_client_id
    FRONTEND_OBJECT_ID                  = var.config.frontend_object_id
    WEBSITES_CONTAINER_START_TIME_LIMIT = "600"
  }
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    require_https          = true
    default_provider       = "azureactivedirectory"
    unauthenticated_action = "Return401"
    excluded_paths         = ["/health"]
    active_directory_v2 {
      client_id            = var.config.mcp_audience
      tenant_auth_endpoint = local.issuer
      allowed_audiences    = [var.config.mcp_audience]
      allowed_applications = [var.config.frontend_client_id]
      allowed_identities   = [var.config.frontend_object_id]
    }
    login { token_store_enabled = false }
  }
  tags = local.tags
}
resource "azurerm_private_endpoint" "mcp" {
  name                = "${local.prefix}-mcp-pe"
  resource_group_name = data.azurerm_resource_group.workload.name
  location            = local.app_location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "mcp"
    private_connection_resource_id = azurerm_linux_web_app.mcp.id
    subresource_names              = ["sites"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "mcp"
    private_dns_zone_ids = [azurerm_private_dns_zone.main["privatelink.azurewebsites.net"].id]
  }
  tags = local.tags
}

resource "azurerm_linux_web_app" "frontend" {
  name                                           = "${local.prefix}-front"
  resource_group_name                            = data.azurerm_resource_group.workload.name
  location                                       = local.app_location
  service_plan_id                                = azurerm_service_plan.main.id
  https_only                                     = true
  virtual_network_subnet_id                      = azurerm_subnet.integration.id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  identity {
    type         = "UserAssigned"
    identity_ids = [var.config.frontend_identity_id]
  }
  site_config {
    always_on                                     = true
    ftps_state                                    = "Disabled"
    minimum_tls_version                           = "1.2"
    health_check_path                             = "/health"
    container_registry_use_managed_identity       = true
    container_registry_managed_identity_client_id = var.config.frontend_client_id
    application_stack {
      docker_registry_url = "https://${azurerm_container_registry.main.login_server}"
      docker_image_name   = "demo:${var.image_tag}"
    }
  }
  app_settings = {
    APP_MODULE                             = "app.frontend:create_app"
    APP_ENV                                = "production"
    APP_VERSION                            = var.image_tag
    WEBSITES_PORT                          = "8000"
    AZURE_TENANT_ID                        = var.config.tenant_id
    AZURE_CLIENT_ID                        = var.config.frontend_client_id
    OPERATOR_OBJECT_ID                     = var.config.operator_object_id
    MCP_URL                                = "https://${local.mcp_hostname}/mcp"
    MCP_SCOPE                              = "api://${var.config.mcp_audience}/.default"
    FOUNDRY_ENDPOINT                       = "https://${local.ai_hostname}"
    MODEL_DEPLOYMENT                       = azurerm_cognitive_deployment.model.name
    FRONTEND_ORIGIN                        = "https://${local.prefix}-front.azurewebsites.net"
    OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID = var.config.frontend_client_id
    WEBSITES_CONTAINER_START_TIME_LIMIT    = "600"
  }
  sticky_settings { app_setting_names = ["OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"] }
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    require_https          = true
    default_provider       = "azureactivedirectory"
    unauthenticated_action = "RedirectToLoginPage"
    excluded_paths         = ["/health"]
    active_directory_v2 {
      client_id                  = var.config.frontend_login_id
      tenant_auth_endpoint       = local.issuer
      client_secret_setting_name = "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"
      allowed_identities         = [var.config.operator_object_id]
    }
    login { token_store_enabled = false }
  }
  tags       = local.tags
  depends_on = [azurerm_private_endpoint.mcp, azurerm_private_endpoint.foundry, azurerm_role_assignment.inference]
}
