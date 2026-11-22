resource "aws_s3_bucket" "st03" {
  bucket = "ict-risk-st03-private-policy"
}

resource "aws_s3_bucket_public_access_block" "st03" {
  bucket                  = aws_s3_bucket.st03.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
