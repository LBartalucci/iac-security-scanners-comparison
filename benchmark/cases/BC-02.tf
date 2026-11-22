resource "aws_ebs_volume" "bc02" {
  availability_zone = "eu-west-1a"
  size              = 20
  encrypted         = true
}
