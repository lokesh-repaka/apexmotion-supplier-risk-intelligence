# ==============================================================================
# ApexMotion Amazon ElastiCache Redis Cluster
# Reference: CLAUDE.md Sec 6 (Redis 7.1, 3 nodes across 3 AZs, multi-AZ failover, TLS)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. ElastiCache Subnet Group (Private Isolated Data Tier)
# ------------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "redis" {
  name        = "apexmotion-${var.environment}-redis-subnet-group"
  description = "ElastiCache Redis subnet group in private data tier"
  subnet_ids  = aws_subnet.data[*].id

  tags = {
    Name = "apexmotion-${var.environment}-redis-subnet-group"
  }
}

# ------------------------------------------------------------------------------
# 2. Redis Replication Group (1 Primary + 2 Read Replicas Multi-AZ)
# ------------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "apexmotion-${var.environment}-redis"
  description          = "ApexMotion Redis Cluster for prompt caching, inventory, and Celery"

  engine             = "redis"
  engine_version     = "7.1"
  node_type          = "cache.r6g.large"
  num_cache_clusters = 3
  port               = 6379

  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis_sg.id]

  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.storage_key.arn
  transit_encryption_enabled = true

  snapshot_retention_limit = 7
  snapshot_window          = "01:00-02:00"
  maintenance_window       = "sun:02:00-sun:03:00"

  tags = {
    Name = "apexmotion-${var.environment}-redis"
  }
}
