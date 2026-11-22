resource "aws_security_group" "nw03" {
  name = "ict-risk-nw03-all-ports-open"

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
