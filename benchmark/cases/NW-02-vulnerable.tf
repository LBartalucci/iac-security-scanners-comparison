resource "aws_security_group" "nw02" {
  name = "ict-risk-nw02-rdp-open"

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
