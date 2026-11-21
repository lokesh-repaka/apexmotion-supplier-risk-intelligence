#!/usr/bin/env bash
# ==============================================================================
# ApexMotion Supplier Risk Intelligence Platform — LocalStack Bootstrap Script
# Provisions:
# 1. Amazon S3 WORM Audit Bucket with Object Lock (COMPLIANCE mode, 7-year retention)
# 2. Amazon S3 Raw Document Bucket for confidential contracts and news
# 3. AWS KMS ECDSA P-256 Key for Human-In-The-Loop (HITL) cryptographic approval tokens
# 4. IAM execution role stubs for API and Worker services
# ==============================================================================

set -euo pipefail

# Configuration defaults
AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-central-1}"
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-mock_access_key}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-mock_secret_key}"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION

log_info() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [INFO] [localstack-bootstrap] $*"
}

log_error() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [ERROR] [localstack-bootstrap] $*" >&2
}

# Unified AWS CLI execution wrapper
aws_cmd() {
    if command -v awslocal &>/dev/null; then
        awslocal "$@"
    else
        aws --endpoint-url="${AWS_ENDPOINT_URL}" --region="${AWS_DEFAULT_REGION}" "$@"
    fi
}

log_info "Initializing ApexMotion LocalStack bootstrap against endpoint: ${AWS_ENDPOINT_URL}"

# ------------------------------------------------------------------------------
# 1. S3 WORM Audit Ledger Bucket (BR-RULE-007, FR-GOV-001)
# ------------------------------------------------------------------------------
WORM_BUCKET="apexmotion-audit-worm"
CONTRACTS_BUCKET="apexmotion-raw-contracts"

log_info "Configuring S3 WORM Audit Bucket: ${WORM_BUCKET}..."

if ! aws_cmd s3api head-bucket --bucket "${WORM_BUCKET}" 2>/dev/null; then
    # In LocalStack / AWS, LocationConstraint is required unless us-east-1
    if [ "${AWS_DEFAULT_REGION}" = "us-east-1" ]; then
        aws_cmd s3api create-bucket \
            --bucket "${WORM_BUCKET}" \
            --object-lock-enabled-for-bucket
    else
        aws_cmd s3api create-bucket \
            --bucket "${WORM_BUCKET}" \
            --create-bucket-configuration LocationConstraint="${AWS_DEFAULT_REGION}" \
            --object-lock-enabled-for-bucket
    fi
    log_info "Created bucket '${WORM_BUCKET}' with Object Lock enabled."
else
    log_info "Bucket '${WORM_BUCKET}' already exists."
fi

# Enforce 7-year COMPLIANCE retention policy (BR-RULE-007)
log_info "Applying 7-year COMPLIANCE Object Lock default retention to '${WORM_BUCKET}'..."
aws_cmd s3api put-object-lock-configuration \
    --bucket "${WORM_BUCKET}" \
    --object-lock-configuration '{
        "ObjectLockEnabled": "Enabled",
        "Rule": {
            "DefaultRetention": {
                "Mode": "COMPLIANCE",
                "Years": 7
            }
        }
    }'
log_info "Object Lock configuration applied successfully."

# Raw documents bucket
log_info "Configuring Raw Contracts S3 Bucket: ${CONTRACTS_BUCKET}..."
if ! aws_cmd s3api head-bucket --bucket "${CONTRACTS_BUCKET}" 2>/dev/null; then
    if [ "${AWS_DEFAULT_REGION}" = "us-east-1" ]; then
        aws_cmd s3api create-bucket --bucket "${CONTRACTS_BUCKET}"
    else
        aws_cmd s3api create-bucket \
            --bucket "${CONTRACTS_BUCKET}" \
            --create-bucket-configuration LocationConstraint="${AWS_DEFAULT_REGION}"
    fi
    log_info "Created bucket '${CONTRACTS_BUCKET}'."
fi

# ------------------------------------------------------------------------------
# 2. AWS KMS ECDSA P-256 Key for HITL Signatures (BR-RULE-001)
# ------------------------------------------------------------------------------
KMS_ALIAS="alias/apexmotion-hitl-signer"
log_info "Configuring AWS KMS ECDSA P-256 Signing Key (${KMS_ALIAS})..."

# Check if alias exists
ALIAS_EXISTS=false
if aws_cmd kms describe-key --key-id "${KMS_ALIAS}" 2>/dev/null; then
    ALIAS_EXISTS=true
    log_info "KMS alias '${KMS_ALIAS}' already exists."
fi

if [ "${ALIAS_EXISTS}" = false ]; then
    KEY_ID=$(aws_cmd kms create-key \
        --key-spec ECC_NIST_P256 \
        --key-usage SIGN_VERIFY \
        --description "ApexMotion HITL ECDSA P-256 Approval Signing Key" \
        --output text \
        --query 'KeyMetadata.KeyId')
    
    log_info "Created KMS Key ID: ${KEY_ID}"

    aws_cmd kms create-alias \
        --alias-name "${KMS_ALIAS}" \
        --target-key-id "${KEY_ID}"
    
    log_info "Created KMS Alias '${KMS_ALIAS}' pointing to Key ID '${KEY_ID}'."
fi

# ------------------------------------------------------------------------------
# 3. IAM Role Stubs (API & Worker Execution)
# ------------------------------------------------------------------------------
TRUST_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": ["ecs-tasks.amazonaws.com", "eks.amazonaws.com", "lambda.amazonaws.com"]
            },
            "Action": "sts:AssumeRole"
        }
    ]
}'

for ROLE_NAME in "apexmotion-api-role" "apexmotion-worker-role"; do
    log_info "Checking IAM role: ${ROLE_NAME}..."
    if ! aws_cmd iam get-role --role-name "${ROLE_NAME}" 2>/dev/null; then
        aws_cmd iam create-role \
            --role-name "${ROLE_NAME}" \
            --assume-role-policy-document "${TRUST_POLICY}" \
            --description "Execution role stub for ${ROLE_NAME}" \
            --output text --query 'Role.Arn'
        log_info "Created IAM role stub '${ROLE_NAME}'."
    else
        log_info "IAM role '${ROLE_NAME}' already exists."
    fi
done

log_info "LocalStack bootstrap sequence completed successfully."
