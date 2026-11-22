resource "aws_iam_policy" "id01" {
  name = "ict-risk-id01-scoped"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "arn:aws:s3:::example-private-bucket/*"
    }]
  })
}
