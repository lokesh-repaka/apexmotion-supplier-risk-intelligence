# ==============================================================================
# ApexMotion S3 Object Lock (WORM Audit Log Archive)
# Reference: CLAUDE.md Sec 6 (7-Year Compliance Mode), HLD Sec 7.2, FRD FMEA-05
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. WORM Audit Log S3 Bucket
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "audit_worm" {
  bucket              = "apexmotion-${var.environment}-audit-log-worm-archive"
  object_lock_enabled = true

  tags = {
    Name       = "apexmotion-${var.environment}-audit-log-worm-archive"
    Compliance = "WORM-Compliance-Mode"
    Retention  = "7-Years"
  }
}

# ------------------------------------------------------------------------------
# 2. Bucket Versioning (Prerequisite for Object Lock)
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_versioning" "audit_worm" {
  bucket = aws_s3_bucket.audit_worm.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ------------------------------------------------------------------------------
# 3. Object Lock Configuration (COMPLIANCE Mode, 7-Year Retention)
# Strict COMPLIANCE mode cannot be overwritten or shortened even by the root user
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_object_lock_configuration" "audit_worm" {
  bucket = aws_s3_bucket.audit_worm.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.audit_retention_years
    }
  }

  depends_on = [aws_s3_bucket_versioning.audit_worm]
}

# ------------------------------------------------------------------------------
# 4. Server-Side Encryption with KMS Customer Managed Key
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_worm" {
  bucket = aws_s3_bucket.audit_worm.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.storage_key.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# ------------------------------------------------------------------------------
# 5. Public Access Block (Strict Isolation)
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_public_access_block" "audit_worm" {
  bucket = aws_s3_bucket.audit_worm.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
