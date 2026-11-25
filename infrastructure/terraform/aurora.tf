# ==============================================================================
# ApexMotion Amazon Aurora PostgreSQL 16 Serverless v2
# Reference: CLAUDE.md Sec 6 (PostgreSQL 16, 0.5-32.0 ACU scaling, Multi-AZ)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. DB Subnet Group (Private Isolated Data Tier)
# ------------------------------------------------------------------------------

resource "aws_db_subnet_group" "aurora" {
  name        = "apexmotion-${var.environment}-aurora-subnet-group"
  description = "Aurora PostgreSQL database subnet group in private data tier"
  subnet_ids  = aws_subnet.data[*].id

  tags = {
    Name = "apexmotion-${var.environment}-aurora-subnet-group"
  }
}

# ------------------------------------------------------------------------------
# 2. Aurora PostgreSQL Cluster (Serverless v2)
# ------------------------------------------------------------------------------

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = "apexmotion-${var.environment}-aurora-pg"
  engine             = "aurora-postgresql"
  engine_version     = "16.2"
  database_name      = "apexmotion"
  master_username    = "apexmotion_admin"

  manage_master_user_password = true

  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora_sg.id]

  storage_encrypted = true
  kms_key_id        = aws_kms_key.storage_key.arn

  backup_retention_period      = 7
  preferred_backup_window      = "02:00-03:00"
  preferred_maintenance_window = "sun:03:00-sun:04:00"
  deletion_protection          = var.environment == "production" ? true : false
  skip_final_snapshot          = var.environment == "production" ? false : true

  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = {
    Name = "apexmotion-${var.environment}-aurora-pg"
  }
}

# ------------------------------------------------------------------------------
# 3. Aurora Cluster Instances (Primary Writer + Read Replica across AZs)
# ------------------------------------------------------------------------------

resource "aws_rds_cluster_instance" "aurora_instances" {
  count              = 2
  identifier         = "apexmotion-${var.environment}-aurora-pg-${count.index}"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  publicly_accessible = false

  tags = {
    Name = "apexmotion-${var.environment}-aurora-pg-${count.index}"
  }
}
