# ==============================================================================
# ApexMotion Amazon Neptune Graph Database (OpenCypher Engine)
# Reference: CLAUDE.md Sec 6 (400k nodes, 3M edges, Port 8182, IAM Auth)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Neptune Subnet Group (Private Isolated Data Tier)
# ------------------------------------------------------------------------------

resource "aws_neptune_subnet_group" "neptune" {
  name        = "apexmotion-${var.environment}-neptune-subnet-group"
  description = "Amazon Neptune database subnet group in private data tier"
  subnet_ids  = aws_subnet.data[*].id

  tags = {
    Name = "apexmotion-${var.environment}-neptune-subnet-group"
  }
}

# ------------------------------------------------------------------------------
# 2. Neptune Parameter Groups (OpenCypher & Query Optimization)
# ------------------------------------------------------------------------------

resource "aws_neptune_cluster_parameter_group" "neptune" {
  name        = "apexmotion-${var.environment}-neptune-cluster-pg"
  family      = "neptune1.3"
  description = "Neptune cluster parameter group with OpenCypher query optimizations"

  parameter {
    name  = "neptune_enable_audit_log"
    value = "1"
  }

  parameter {
    name  = "neptune_query_timeout"
    value = "120000"
  }

  tags = {
    Name = "apexmotion-${var.environment}-neptune-cluster-pg"
  }
}

# ------------------------------------------------------------------------------
# 3. Amazon Neptune Cluster (Multi-AZ Knowledge Graph)
# ------------------------------------------------------------------------------

resource "aws_neptune_cluster" "graph" {
  cluster_identifier                   = "apexmotion-${var.environment}-neptune-graph"
  engine                               = "neptune"
  engine_version                       = "1.3.0.0"
  port                                 = 8182
  neptune_subnet_group_name            = aws_neptune_subnet_group.neptune.name
  vpc_security_group_ids               = [aws_security_group.neptune_sg.id]
  neptune_cluster_parameter_group_name = aws_neptune_cluster_parameter_group.neptune.name

  storage_encrypted = true
  kms_key_arn       = aws_kms_key.storage_key.arn

  iam_database_authentication_enabled = true
  backup_retention_period             = 7
  preferred_backup_window             = "03:00-04:00"
  preferred_maintenance_window        = "sun:04:00-sun:05:00"
  deletion_protection                 = var.environment == "production" ? true : false
  skip_final_snapshot                 = var.environment == "production" ? false : true

  tags = {
    Name = "apexmotion-${var.environment}-neptune-graph"
  }
}

# ------------------------------------------------------------------------------
# 4. Neptune Cluster Instances (Primary Writer + Read Replica across AZs)
# ------------------------------------------------------------------------------

resource "aws_neptune_cluster_instance" "instances" {
  count              = 2
  identifier         = "apexmotion-${var.environment}-neptune-instance-${count.index}"
  cluster_identifier = aws_neptune_cluster.graph.id
  instance_class     = "db.r6g.xlarge"
  engine             = "neptune"

  publicly_accessible = false

  tags = {
    Name = "apexmotion-${var.environment}-neptune-instance-${count.index}"
  }
}
