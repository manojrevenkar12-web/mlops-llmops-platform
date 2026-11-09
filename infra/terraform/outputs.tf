output "capture_bucket" {
  value = aws_s3_bucket.capture.bucket
}

output "guardrail_id" {
  value = aws_bedrock_guardrail.customer_service.guardrail_id
}

output "control_plane_role_arn" {
  value = aws_iam_role.control_plane.arn
}
