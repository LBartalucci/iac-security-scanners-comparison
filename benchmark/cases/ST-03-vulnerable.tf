resource "aws_s3_bucket" "st03" {
  bucket = "ict-risk-st03-public-policy"
}

resource "aws_s3_bucket_policy" "st03" {
  bucket = aws_s3_bucket.st03.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.st03.arn}/*"
    }]
  })
}
