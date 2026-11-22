resource "aws_security_group" "bc04" {
  name = "ict-risk-bc04-private"

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}
