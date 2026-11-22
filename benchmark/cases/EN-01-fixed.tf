resource "aws_s3_bucket" "en01" {
  bucket = "ict-risk-en01-encrypted"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "en01" {
  bucket = aws_s3_bucket.en01.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
