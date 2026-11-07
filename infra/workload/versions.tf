terraform {
  required_version = ">= 1.14, < 2.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "= 5.13.0" }
    azuread = { source = "hashicorp/azuread", version = "= 3.10.0" }
  }
  backend "azurerm" {
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {
    cognitive_account {
      purge_soft_delete_on_destroy = false
    }
  }
  subscription_id                 = var.config.subscription_id
  resource_provider_registrations = "none"
}

provider "azuread" {
  tenant_id = var.config.tenant_id
}
