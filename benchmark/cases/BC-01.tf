resource "aws_s3_bucket" "bc01" {
  bucket = "ict-risk-bc01-private"
}

resource "aws_s3_bucket_public_access_block" "bc01" {
  bucket                  = aws_s3_bucket.bc01.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bc01" {
  bucket = aws_s3_bucket.bc01.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
