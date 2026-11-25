# ==============================================================================
# ApexMotion Amazon MSK Kafka Cluster (3-Broker Multi-AZ)
# Reference: CLAUDE.md Sec 6 (3 brokers across 3 AZs, 1.11M/day, 1,285 ev/s burst, TLS)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. CloudWatch Log Group for MSK Broker Logs
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "msk_logs" {
  name              = "/aws/msk/apexmotion-${var.environment}-kafka"
  retention_in_days = 30

  tags = {
    Name = "apexmotion-${var.environment}-msk-log-group"
  }
}

# ------------------------------------------------------------------------------
# 2. Amazon MSK Kafka Cluster (3-Broker Multi-AZ)
# ------------------------------------------------------------------------------

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "apexmotion-${var.environment}-msk"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.m7g.large"
    client_subnets  = aws_subnet.data[*].id
    security_groups = [aws_security_group.msk_sg.id]

    storage_info {
      ebs_storage_info {
        volume_size = 1000
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
    encryption_at_rest_kms_key_arn = aws_kms_key.storage_key.arn
  }

  open_monitoring {
    prometheus {
      jmx_exporter {
        enabled_in_broker = true
      }
      node_exporter {
        enabled_in_broker = true
      }
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_logs.name
      }
    }
  }

  tags = {
    Name = "apexmotion-${var.environment}-msk"
  }
}
