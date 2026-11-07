terraform {
  required_version = ">= 1.14, < 2.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "= 5.13.0" }
    azuread = { source = "hashicorp/azuread", version = "= 3.10.0" }
  }
  backend "local" {
    path = "../../.local/bootstrap.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}

provider "azuread" {
  tenant_id = var.tenant_id
}
