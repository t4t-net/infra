data "aws_iam_policy_document" "this" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = ["*"]

    resources = [aws_kms_key.this.arn]
  }

  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["${aws_iam_user.this.arn}"]
    }

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]

    resources = [aws_kms_key.this.arn]
  }
}

resource "aws_kms_key" "this" {
  description             = "OpenBao sealing key"
  enable_key_rotation     = true
  deletion_window_in_days = 10
}

resource "aws_kms_key_policy" "this" {
  key_id = aws_kms_key.this.key_id
  policy = data.aws_iam_policy_document.this.json
}

output "kms_key_id" {
  value = aws_kms_key.this.key_id
}

