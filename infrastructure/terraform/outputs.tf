# ==============================================================================
# ApexMotion Terraform Outputs
# Reference: TASKS.md (P16-3), CLAUDE.md Sec 6, and HLD Sec 6 & 7
# ==============================================================================

output "vpc_id" {
  description = "ID of the isolated enterprise VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public DMZ subnets"
  value       = aws_subnet.public[*].id
}

output "application_subnet_ids" {
  description = "IDs of the private application (EKS) subnets"
  value       = aws_subnet.application[*].id
}

output "data_subnet_ids" {
  description = "IDs of the isolated private data subnets"
  value       = aws_subnet.data[*].id
}

output "eks_cluster_name" {
  description = "Name identifier of the Amazon EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "Kubernetes API endpoint for the EKS cluster"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_certificate_authority" {
  description = "Certificate authority data for the EKS cluster"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "aurora_endpoint" {
  description = "Writer endpoint for Aurora PostgreSQL Serverless v2 cluster"
  value       = aws_rds_cluster.aurora.endpoint
}

output "aurora_reader_endpoint" {
  description = "Reader endpoint for Aurora PostgreSQL Serverless v2 cluster"
  value       = aws_rds_cluster.aurora.reader_endpoint
}

output "neptune_endpoint" {
  description = "Endpoint for Amazon Neptune OpenCypher graph cluster"
  value       = aws_neptune_cluster.graph.endpoint
}

output "neptune_port" {
  description = "Port number for Amazon Neptune cluster (8182)"
  value       = aws_neptune_cluster.graph.port
}

output "msk_bootstrap_brokers" {
  description = "TLS connection host:port string for Amazon MSK cluster"
  value       = aws_msk_cluster.kafka.bootstrap_brokers_tls
}

output "msk_cluster_arn" {
  description = "ARN identifier for Amazon MSK cluster"
  value       = aws_msk_cluster.kafka.arn
}

output "opensearch_endpoint" {
  description = "Endpoint domain for Amazon OpenSearch vector search cluster"
  value       = aws_opensearch_domain.vector_search.endpoint
}

output "redis_endpoint" {
  description = "Primary endpoint address for Amazon ElastiCache Redis cluster"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "s3_worm_bucket_name" {
  description = "Name of the S3 Object Lock WORM audit log bucket"
  value       = aws_s3_bucket.audit_worm.id
}

output "s3_worm_bucket_arn" {
  description = "ARN of the S3 Object Lock WORM audit log bucket"
  value       = aws_s3_bucket.audit_worm.arn
}

output "kms_hitl_key_arn" {
  description = "ARN of the ECDSA P-256 KMS key for HITL spend authorization tokens"
  value       = aws_kms_key.hitl_token_key.arn
}

output "kms_storage_key_arn" {
  description = "ARN of the AES-256 KMS key for at-rest data store encryption"
  value       = aws_kms_key.storage_key.arn
}
