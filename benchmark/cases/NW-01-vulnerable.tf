resource "aws_security_group" "nw01" {
  name = "ict-risk-nw01-ssh-open"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
