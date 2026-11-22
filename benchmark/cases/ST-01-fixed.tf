resource "aws_s3_bucket" "st01" {
  bucket = "ict-risk-st01-private-acl"
}

resource "aws_s3_bucket_public_access_block" "st01" {
  bucket                  = aws_s3_bucket.st01.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
