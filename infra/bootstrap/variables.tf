variable "subscription_id" { type = string }
variable "tenant_id" { type = string }
variable "repository" { type = string }
variable "github_subject" { type = string }
variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^azmcp[a-z0-9]{6}$", var.prefix))
    error_message = "Use azmcp followed by six lowercase alphanumeric characters."
  }
}
variable "location" { default = "japaneast" }
variable "app_location" {
  type    = string
  default = null
}
variable "expires_at" { type = string }
