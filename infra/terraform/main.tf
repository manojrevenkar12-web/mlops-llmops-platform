data "aws_caller_identity" "me" {}

locals {
  account = data.aws_caller_identity.me.account_id
}

# Data capture from SageMaker shadow and canary variants: the input to the online/offline parity check.
resource "aws_s3_bucket" "capture" {
  bucket = "paved-capture-${local.account}-${var.region}"
}

resource "aws_s3_bucket_public_access_block" "capture" {
  bucket                  = aws_s3_bucket.capture.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "capture" {
  bucket = aws_s3_bucket.capture.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "capture" {
  bucket = aws_s3_bucket.capture.id
  rule {
    id     = "expire-capture"
    status = "Enabled"
    filter {
      prefix = "capture/"
    }
    expiration {
      days = 30
    }
  }
}

# Guardrail every agent on the platform calls through.
resource "aws_bedrock_guardrail" "customer_service" {
  name                      = "paved-customer-service"
  blocked_input_messaging   = "Sorry, I can't help with that message."
  blocked_outputs_messaging = "Sorry, I can't answer that. A colleague will get back to you."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "IBAN"
      action = "ANONYMIZE"
    }
  }
}

# One budget per team on the cost-allocation tag the platform writes on every endpoint and inference profile.
resource "aws_budgets_budget" "team" {
  for_each     = var.teams
  name         = "paved-team-${each.key}"
  budget_type  = "COST"
  limit_amount = tostring(each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:team$%s", each.key)]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
