resource "aws_iam_policy" "id02" {
  name = "ict-risk-id02-passrole-scoped"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "iam:PassRole"
      Resource = "arn:aws:iam::123456789012:role/application-role"
    }]
  })
}
