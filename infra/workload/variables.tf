variable "config" {
  type = object({
    subscription_id         = string
    tenant_id               = string
    prefix                  = string
    location                = string
    expires_at              = string
    resource_group_name     = string
    frontend_identity_id    = string
    frontend_client_id      = string
    frontend_object_id      = string
    mcp_identity_id         = string
    mcp_client_id           = string
    mcp_object_id           = string
    frontend_login_id       = string
    frontend_application_id = string
    mcp_audience            = string
    operator_object_id      = string
    deployer_object_id      = string
  })
}
variable "image_tag" {
  type    = string
  default = "bootstrap"
}
variable "model_name" {
  type    = string
  default = "gpt-4.1-mini"
}
variable "model_version" {
  type    = string
  default = "2025-04-14"
}
