# ==============================================================================
# ApexMotion Amazon OpenSearch Vector Search Cluster
# Reference: CLAUDE.md Sec 6 (3M chunks, 1536-dim k-NN, 3 nodes across 3 AZs)
# ==============================================================================

resource "aws_opensearch_domain" "vector_search" {
  domain_name    = "apexmotion-${var.environment}-vectors"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type          = "r6g.large.search"
    instance_count         = 3
    zone_awareness_enabled = true

    zone_awareness_config {
      availability_zone_count = 3
    }
  }

  vpc_options {
    subnet_ids         = aws_subnet.data[*].id
    security_group_ids = [aws_security_group.opensearch_sg.id]
  }

  encrypt_at_rest {
    enabled    = true
    kms_key_id = aws_kms_key.storage_key.arn
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 100
  }

  advanced_options = {
    "indices.query.bool.max_clause_count"    = "1024"
    "rest.action.multi.allow_explicit_index" = "true"
  }

  tags = {
    Name = "apexmotion-${var.environment}-vectors"
  }
}
