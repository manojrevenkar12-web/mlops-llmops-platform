# The control plane's role: it may only touch resources the platform manages, and only the calls the release
# path makes (create model and endpoint configs, move variant weights, point AgentCore endpoints, tag profiles).
data "aws_iam_policy_document" "control_plane_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "control_plane" {
  name               = "paved-control-plane"
  assume_role_policy = data.aws_iam_policy_document.control_plane_assume.json
}

data "aws_iam_policy_document" "control_plane" {
  statement {
    sid = "SageMakerReleasePath"
    actions = [
      "sagemaker:CreateModel",
      "sagemaker:CreateEndpointConfig",
      "sagemaker:UpdateEndpoint",
      "sagemaker:UpdateEndpointWeightsAndCapacities",
      "sagemaker:DescribeEndpoint",
      "sagemaker:AddTags",
    ]
    resources = ["arn:aws:sagemaker:${var.region}:${local.account}:*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/managed-by"
      values   = ["paved"]
    }
  }
  statement {
    sid       = "BedrockProfiles"
    actions   = ["bedrock:CreateInferenceProfile", "bedrock:TagResource", "bedrock:GetInferenceProfile"]
    resources = ["arn:aws:bedrock:${var.region}:${local.account}:application-inference-profile/*"]
  }
  statement {
    sid       = "AgentCoreEndpoints"
    actions   = ["bedrock-agentcore:UpdateAgentRuntimeEndpoint", "bedrock-agentcore:GetAgentRuntimeEndpoint"]
    resources = ["arn:aws:bedrock-agentcore:${var.region}:${local.account}:runtime/*"]
  }
  statement {
    sid       = "ReadCapture"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.capture.arn, "${aws_s3_bucket.capture.arn}/*"]
  }
}

resource "aws_iam_role_policy" "control_plane" {
  name   = "release-path"
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane.json
}

# GitHub Actions in the platform repository may validate and hand over releases; nothing else.
data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${local.account}:oidc-provider/token.actions.githubusercontent.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_release" {
  name               = "paved-github-release"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}
