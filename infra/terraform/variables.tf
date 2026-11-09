variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "github_repository" {
  description = "owner/repo whose workflows may hand releases to the control plane"
  type        = string
  default     = "manojrevenkar12-web/mlops-llmops-platform"
}

variable "teams" {
  description = "Teams on the platform and their monthly budget in USD (the sum of their workloads' budgets)"
  type        = map(number)
  default = {
    pricing         = 900
    "cs-automation" = 25000
    damage          = 300
    "revenue-mgmt"  = 400
    "fleet-ops"     = 400
  }
}

variable "budget_alert_email" {
  type    = string
  default = "mlops-platform@example.com"
}
