# ==============================================================================
# ApexMotion AWS KMS Cryptographic Infrastructure
# Reference: BR-RULE-001 (ECDSA P-256 for HITL tokens), CLAUDE.md Sec 6 & 11
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Asymmetric KMS Key for HITL Spend Authorization (ECDSA P-256)
# ------------------------------------------------------------------------------

resource "aws_kms_key" "hitl_token_key" {
  description              = "ApexMotion KMS ECDSA P-256 key for cryptographically verified HITL spend approval tokens (BR-RULE-001)"
  customer_master_key_spec = "ECC_NIST_P256"
  key_usage                = "SIGN_VERIFY"
  deletion_window_in_days  = 30

  tags = {
    Name       = "apexmotion-${var.environment}-hitl-signing-key"
    Compliance = "BR-RULE-001"
    Security   = "Cryptographic-HITL-Gate"
  }
}

resource "aws_kms_alias" "hitl_token_key_alias" {
  name          = "alias/apexmotion-${var.environment}-hitl-signing-key"
  target_key_id = aws_kms_key.hitl_token_key.key_id
}

# ------------------------------------------------------------------------------
# 2. Symmetric KMS Key for Storage Encryption at Rest (AES-256)
# ------------------------------------------------------------------------------

resource "aws_kms_key" "storage_key" {
  description              = "ApexMotion AES-256 KMS key for at-rest storage encryption (Aurora, Neptune, MSK, OpenSearch, S3)"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  key_usage                = "ENCRYPT_DECRYPT"
  deletion_window_in_days  = 30
  enable_key_rotation      = true

  tags = {
    Name       = "apexmotion-${var.environment}-storage-encryption-key"
    Compliance = "ISO-27001"
    Security   = "At-Rest-Encryption"
  }
}

resource "aws_kms_alias" "storage_key_alias" {
  name          = "alias/apexmotion-${var.environment}-storage-encryption-key"
  target_key_id = aws_kms_key.storage_key.key_id
}
