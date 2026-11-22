resource "aws_ebs_volume" "en02" {
  availability_zone = "eu-west-1a"
  size              = 20
  encrypted         = true
}
