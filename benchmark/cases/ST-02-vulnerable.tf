resource "aws_s3_bucket" "st02" {
  bucket = "ict-risk-st02-public-block-disabled"
}

resource "aws_s3_bucket_public_access_block" "st02" {
  bucket                  = aws_s3_bucket.st02.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}
