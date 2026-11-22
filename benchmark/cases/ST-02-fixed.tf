resource "aws_s3_bucket" "st02" {
  bucket = "ict-risk-st02-public-block-enabled"
}

resource "aws_s3_bucket_public_access_block" "st02" {
  bucket                  = aws_s3_bucket.st02.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
