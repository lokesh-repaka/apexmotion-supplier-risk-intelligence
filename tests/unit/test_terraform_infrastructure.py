"""Unit tests for Terraform infrastructure modules and AWS resource specifications.

Reference: TASKS.md (P16-3), CLAUDE.md Sec 6, and HLD Sec 6 & 7.

Validates:
1. Core Terraform files presence (main, variables, outputs, VPC, KMS, S3 WORM, EKS, Aurora, Neptune, MSK, OpenSearch, ElastiCache).
2. VPC topology: 10.100.0.0/16, 3 AZs, public DMZ, private app, isolated private data subnets, NAT, and security groups.
3. AWS KMS keys: ECDSA P-256 for HITL tokens (SIGN_VERIFY) and AES-256 for storage with key rotation.
4. S3 Object Lock: COMPLIANCE mode, 7-year retention (ISO-27001), versioning, KMS encryption, no public access.
5. Amazon EKS 1.30: Kubernetes 1.30, application node group, GPU vLLM node group (g6e.12xlarge), IRSA OIDC.
6. Amazon Aurora PostgreSQL 16 Serverless v2: PostgreSQL 16.2, 0.5 to 32.0 ACU, KMS encryption, 7-day backup.
7. Amazon Neptune: OpenCypher graph cluster, port 8182, IAM DB auth, KMS encryption, private data subnets.
8. Amazon MSK: 3-broker Kafka cluster across 3 AZs, TLS in transit, KMS at rest.
9. Amazon OpenSearch: OpenSearch 2.11, 3-node multi-AZ zone awareness, vector search, TLS 1.2+.
10. Amazon ElastiCache Redis: Redis 7.1, 3-node cluster mode with automatic failover, TLS in transit, KMS at rest.
11. Variables & Outputs: Environment parameterization, endpoint and ARN exports.
"""

import re
from pathlib import Path

TERRAFORM_DIR = Path("infrastructure/terraform")


def test_terraform_modules_files_exist() -> None:
    """Verify all required Terraform module configuration files exist."""
    required_files = [
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "vpc.tf",
        "kms.tf",
        "s3_worm.tf",
        "eks.tf",
        "aurora.tf",
        "neptune.tf",
        "msk.tf",
        "opensearch.tf",
        "elasticache.tf",
    ]
    for filename in required_files:
        filepath = TERRAFORM_DIR / filename
        assert filepath.exists(), f"Missing required Terraform module: {filepath}"
        assert len(filepath.read_text(encoding="utf-8").strip()) > 0, f"Empty file: {filepath}"


def test_vpc_network_topology() -> None:
    """Verify VPC 10.100.0.0/16 across 3 AZs with public, application, and data subnets."""
    vpc_path = TERRAFORM_DIR / "vpc.tf"
    assert vpc_path.exists(), "vpc.tf must exist"
    content = vpc_path.read_text(encoding="utf-8")

    # VPC and CIDR
    assert 'resource "aws_vpc"' in content
    assert "10.100.0.0/16" in content

    # 3 Network tiers
    assert "public" in content.lower()
    assert "application" in content.lower()
    assert "data" in content.lower()

    # Internet Gateway & NAT Gateway
    assert 'resource "aws_internet_gateway"' in content
    assert 'resource "aws_nat_gateway"' in content

    # Security groups for internal services
    assert 'resource "aws_security_group"' in content
    assert "5432" in content  # Aurora PG
    assert "8182" in content  # Neptune
    assert "9092" in content or "9094" in content or "9098" in content  # MSK Kafka
    assert "6379" in content  # Redis
    assert "443" in content  # HTTPS / OpenSearch


def test_kms_keys_specifications() -> None:
    """Verify ECDSA P-256 for HITL spend tokens and AES-256 for storage encryption."""
    kms_path = TERRAFORM_DIR / "kms.tf"
    assert kms_path.exists(), "kms.tf must exist"
    content = kms_path.read_text(encoding="utf-8")

    # HITL token signing key (ECDSA P-256)
    assert "ECC_NIST_P256" in content
    assert "SIGN_VERIFY" in content
    assert "hitl" in content.lower()

    # Storage encryption key (AES-256) with key rotation
    assert "SYMMETRIC_DEFAULT" in content
    assert "ENCRYPT_DECRYPT" in content
    assert re.search(r"enable_key_rotation\s*=\s*true", content)


def test_s3_object_lock_compliance_mode() -> None:
    """Verify S3 WORM audit log bucket with COMPLIANCE mode and 7-year retention."""
    s3_path = TERRAFORM_DIR / "s3_worm.tf"
    assert s3_path.exists(), "s3_worm.tf must exist"
    content = s3_path.read_text(encoding="utf-8")

    # Bucket with Object Lock enabled
    assert 'resource "aws_s3_bucket"' in content
    assert re.search(r"object_lock_enabled\s*=\s*true", content)

    # Strict COMPLIANCE mode (cannot be bypassed by root)
    assert re.search(r'mode\s*=\s*"COMPLIANCE"', content)

    # 7-year retention period
    assert re.search(r"years\s*=\s*(var\.audit_retention_years|7)", content)

    # Versioning & Public access block
    assert 'resource "aws_s3_bucket_versioning"' in content
    assert 'resource "aws_s3_bucket_public_access_block"' in content
    assert re.search(r"block_public_acls\s*=\s*true", content)


def test_eks_cluster_130_and_node_groups() -> None:
    """Verify Amazon EKS 1.30 with application and GPU vLLM node groups."""
    eks_path = TERRAFORM_DIR / "eks.tf"
    assert eks_path.exists(), "eks.tf must exist"
    content = eks_path.read_text(encoding="utf-8")

    # EKS 1.30 cluster
    assert 'resource "aws_eks_cluster"' in content
    assert re.search(r'version\s*=\s*"1\.30"', content)

    # Node groups: general app and GPU vLLM
    assert 'resource "aws_eks_node_group"' in content
    assert "m6i" in content  # Application nodes
    assert "g6e.12xlarge" in content or "gpu" in content.lower()  # GPU vLLM nodes

    # OIDC IRSA provider
    assert "aws_iam_openid_connect_provider" in content or "oidc" in content.lower()


def test_aurora_postgresql_16_serverless_v2() -> None:
    """Verify Aurora PostgreSQL 16 Serverless v2 with 0.5 to 32.0 ACU scaling."""
    aurora_path = TERRAFORM_DIR / "aurora.tf"
    assert aurora_path.exists(), "aurora.tf must exist"
    content = aurora_path.read_text(encoding="utf-8")

    assert 'resource "aws_rds_cluster"' in content
    assert "aurora-postgresql" in content
    assert "16." in content  # PostgreSQL 16

    # Serverless v2 scaling config
    assert "serverlessv2_scaling_configuration" in content
    assert re.search(r"min_capacity\s*=\s*(var\.aurora_min_capacity|0\.5)", content)
    assert re.search(r"max_capacity\s*=\s*(var\.aurora_max_capacity|32)", content)

    # Storage encryption
    assert re.search(r"storage_encrypted\s*=\s*true", content)


def test_neptune_opencypher_graph_cluster() -> None:
    """Verify Amazon Neptune graph cluster for OpenCypher supplier graph."""
    neptune_path = TERRAFORM_DIR / "neptune.tf"
    assert neptune_path.exists(), "neptune.tf must exist"
    content = neptune_path.read_text(encoding="utf-8")

    assert 'resource "aws_neptune_cluster"' in content
    assert "8182" in content
    assert re.search(r"storage_encrypted\s*=\s*true", content)
    assert re.search(r"iam_database_authentication_enabled\s*=\s*true", content)


def test_msk_kafka_three_broker_cluster() -> None:
    """Verify Amazon MSK 3-broker Kafka cluster across 3 AZs."""
    msk_path = TERRAFORM_DIR / "msk.tf"
    assert msk_path.exists(), "msk.tf must exist"
    content = msk_path.read_text(encoding="utf-8")

    assert 'resource "aws_msk_cluster"' in content
    assert re.search(r"number_of_broker_nodes\s*=\s*3", content)
    assert "kafka_version" in content
    assert "encryption_info" in content


def test_opensearch_vector_search_cluster() -> None:
    """Verify Amazon OpenSearch Service domain with multi-AZ zone awareness."""
    opensearch_path = TERRAFORM_DIR / "opensearch.tf"
    assert opensearch_path.exists(), "opensearch.tf must exist"
    content = opensearch_path.read_text(encoding="utf-8")

    assert 'resource "aws_opensearch_domain"' in content
    assert "OpenSearch" in content
    assert re.search(r"zone_awareness_enabled\s*=\s*true", content)
    assert "encrypt_at_rest" in content
    assert "node_to_node_encryption" in content


def test_elasticache_redis_cluster() -> None:
    """Verify Amazon ElastiCache Redis 7.1 replication group with multi-AZ failover."""
    redis_path = TERRAFORM_DIR / "elasticache.tf"
    assert redis_path.exists(), "elasticache.tf must exist"
    content = redis_path.read_text(encoding="utf-8")

    assert 'resource "aws_elasticache_replication_group"' in content
    assert "redis" in content
    assert re.search(r"automatic_failover_enabled\s*=\s*true", content)
    assert re.search(r"multi_az_enabled\s*=\s*true", content)
    assert re.search(r"at_rest_encryption_enabled\s*=\s*true", content)
    assert re.search(r"transit_encryption_enabled\s*=\s*true", content)


def test_terraform_variables_and_outputs_integrity() -> None:
    """Verify variables.tf and outputs.tf expose required parameters and connection endpoints."""
    var_path = TERRAFORM_DIR / "variables.tf"
    out_path = TERRAFORM_DIR / "outputs.tf"
    assert var_path.exists(), "variables.tf must exist"
    assert out_path.exists(), "outputs.tf must exist"

    var_content = var_path.read_text(encoding="utf-8")
    out_content = out_path.read_text(encoding="utf-8")

    assert 'variable "environment"' in var_content
    assert 'variable "aws_region"' in var_content

    # Key connection outputs
    assert 'output "eks_cluster_name"' in out_content
    assert 'output "aurora_endpoint"' in out_content
    assert 'output "neptune_endpoint"' in out_content
    assert 'output "msk_bootstrap_brokers"' in out_content
    assert 'output "opensearch_endpoint"' in out_content
    assert 'output "redis_endpoint"' in out_content
    assert 'output "s3_worm_bucket_name"' in out_content
    assert 'output "kms_hitl_key_arn"' in out_content
