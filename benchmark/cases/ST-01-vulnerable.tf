resource "aws_s3_bucket" "st01" {
  bucket = "ict-risk-st01-public-acl"
}

resource "aws_s3_bucket_acl" "st01" {
  bucket = aws_s3_bucket.st01.id
  acl    = "public-read"
}
