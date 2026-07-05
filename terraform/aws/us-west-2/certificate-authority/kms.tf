data "aws_iam_policy_document" "ssh-user-ca" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = ["*"]

    resources = [data.aws_kms_key.ssh-user-ca.arn]
  }

  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["${aws_iam_user.this.arn}"]
    }

    actions = [
      "kms:GetPublicKey",
      "kms:Sign"
    ]

    resources = [data.aws_kms_key.ssh-user-ca.arn]
  }
}

data "aws_kms_key" "ssh-user-ca" {
  key_id = "a369ada2-91e7-40fa-a40d-97b4613585cd"
}

resource "aws_kms_key_policy" "ssh-user-ca" {
  key_id = data.aws_kms_key.ssh-user-ca.key_id
  policy = data.aws_iam_policy_document.ssh-user-ca.json
}

data "aws_kms_key" "root-ca" {
  key_id = "af471c40-bb92-415c-8f4f-e4048d779350"
}

# resource "aws_kms_key_policy" "root-ca" {
#   key_id = data.aws_kms_key.ssh-user-ca.key_id
#   policy = data.aws_iam_policy_document.ca-kms.json
# }

data "aws_iam_policy_document" "intermediate-ca" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = ["*"]

    resources = [data.aws_kms_key.intermediate-ca.arn]
  }

  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["${aws_iam_user.this.arn}"]
    }

    actions = [
      "kms:GetPublicKey",
      "kms:Sign"
    ]

    resources = [data.aws_kms_key.intermediate-ca.arn]
  }
}

data "aws_kms_key" "intermediate-ca" {
  key_id = "e21f49a2-ef9f-4e87-9291-f5796f88727e"
}

resource "aws_kms_key_policy" "intermediate-ca" {
  key_id = data.aws_kms_key.intermediate-ca.key_id
  policy = data.aws_iam_policy_document.intermediate-ca.json
}

data "aws_iam_policy_document" "ssh-host-ca" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = ["*"]

    resources = [data.aws_kms_key.ssh-host-ca.arn]
  }

  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["${aws_iam_user.this.arn}"]
    }

    actions = [
      "kms:GetPublicKey",
      "kms:Sign"
    ]

    resources = [data.aws_kms_key.ssh-host-ca.arn]
  }
}

data "aws_kms_key" "ssh-host-ca" {
  key_id = "f4f61975-422d-4f32-be56-33fe4a478b8e"
}

resource "aws_kms_key_policy" "ssh-host-ca" {
  key_id = data.aws_kms_key.ssh-host-ca.key_id
  policy = data.aws_iam_policy_document.ssh-host-ca.json
}

