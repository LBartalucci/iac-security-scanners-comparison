resource "aws_security_group" "nw03" {
  name = "ict-risk-nw03-private-https"

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}
