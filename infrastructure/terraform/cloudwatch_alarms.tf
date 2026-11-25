# ==============================================================================
# ApexMotion CloudWatch Alarms & Operational Alerting Infrastructure
# Reference: TASKS.md (P15-5), LLD Sec 8.3, and FRD FMEA-04
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "environment" {
  type        = string
  description = "Target deployment environment (production, staging, dev)"
  default     = "production"
}

variable "aws_region" {
  type        = string
  description = "AWS region for CloudWatch metric alarms"
  default     = "us-east-1"
}

# ------------------------------------------------------------------------------
# 1. Alert Notification SNS Topics (PagerDuty & Platform Ops)
# ------------------------------------------------------------------------------

resource "aws_sns_topic" "p1_pagerduty" {
  name         = "apexmotion-${var.environment}-p1-pagerduty-alarms"
  display_name = "ApexMotion P1 PagerDuty Alarms (${var.environment})"

  tags = {
    Environment = var.environment
    Service     = "apexmotion-risk-intelligence"
    Severity    = "P1-Critical"
    ManagedBy   = "Terraform"
  }
}

resource "aws_sns_topic" "p2_platform_ops" {
  name         = "apexmotion-${var.environment}-p2-platform-ops-alarms"
  display_name = "ApexMotion P2 Platform Ops Alarms (${var.environment})"

  tags = {
    Environment = var.environment
    Service     = "apexmotion-risk-intelligence"
    Severity    = "P2-High"
    ManagedBy   = "Terraform"
  }
}

# ------------------------------------------------------------------------------
# 2. Critical Alarm: Investigation SLA Breach (p95 > 90s)
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "p95_investigation_latency" {
  alarm_name          = "apexmotion-${var.environment}-p95-investigation-latency"
  alarm_description   = "Critical SLO Breach: p95 investigation duration exceeds 90s SLA boundary for 2 consecutive periods (PRD Sec 14, FRD FR-DEC-001)."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 90
  datapoints_to_alarm = 2
  treat_missing_data  = "missing"
  alarm_actions       = [aws_sns_topic.p1_pagerduty.arn]
  ok_actions          = [aws_sns_topic.p1_pagerduty.arn]

  metric_name        = "InvestigationDurationSeconds"
  namespace          = "ApexMotion/Platform"
  period             = 60
  extended_statistic = "p95"

  dimensions = {
    Service     = "investigation-orchestrator"
    Environment = var.environment
  }

  tags = {
    Environment = var.environment
    SLO         = "p95-investigation-latency"
    Severity    = "P1-Critical"
  }
}

# ------------------------------------------------------------------------------
# 3. High Severity: API 5xx Error Rate Breach (> 1.0%)
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_error_rate" {
  alarm_name          = "apexmotion-${var.environment}-api-error-rate"
  alarm_description   = "High Severity: FastAPI inbound HTTP 5xx error rate exceeds 1.0% across 2 evaluation periods."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 1
  datapoints_to_alarm = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.p1_pagerduty.arn]
  ok_actions          = [aws_sns_topic.p1_pagerduty.arn]

  metric_query {
    id          = "e1"
    expression  = "(m2 / m1) * 100"
    label       = "ErrorRatePercentage"
    return_data = "true"
  }

  metric_query {
    id = "m1"
    metric {
      metric_name = "RequestCount"
      namespace   = "ApexMotion/Platform"
      period      = 60
      stat        = "Sum"
      dimensions = {
        Service     = "fastapi-gateway"
        Environment = var.environment
      }
    }
  }

  metric_query {
    id = "m2"
    metric {
      metric_name = "HTTPCode_5XX_Count"
      namespace   = "ApexMotion/Platform"
      period      = 60
      stat        = "Sum"
      dimensions = {
        Service     = "fastapi-gateway"
        Environment = var.environment
      }
    }
  }

  tags = {
    Environment = var.environment
    Service     = "api-gateway"
    Severity    = "P1-Critical"
  }
}

# ------------------------------------------------------------------------------
# 4. High Severity: Kafka Consumer Lag Breach (> 30s)
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "kafka_consumer_lag" {
  alarm_name          = "apexmotion-${var.environment}-kafka-consumer-lag"
  alarm_description   = "High Severity: Kafka consumer lag exceeds 30s for 3 periods, triggering KEDA worker autoscaling (LLD Sec 8.3)."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 30
  datapoints_to_alarm = 3
  treat_missing_data  = "missing"
  alarm_actions       = [aws_sns_topic.p2_platform_ops.arn]
  ok_actions          = [aws_sns_topic.p2_platform_ops.arn]

  metric_name = "EstimatedMaxTimeLag"
  namespace   = "ApexMotion/Kafka"
  period      = 60
  statistic   = "Maximum"

  dimensions = {
    ConsumerGroup = "apexmotion-disruption-consumers"
    Environment   = var.environment
  }

  tags = {
    Environment = var.environment
    Component   = "kafka-consumer"
    Severity    = "P2-High"
  }
}

# ------------------------------------------------------------------------------
# 5. High Severity: Neptune Query Latency (> 2.0s / 2000ms)
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "neptune_query_latency" {
  alarm_name          = "apexmotion-${var.environment}-neptune-query-latency"
  alarm_description   = "High Severity: Amazon Neptune OpenCypher query latency exceeds 2.0s across 2 evaluation periods."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 2
  datapoints_to_alarm = 2
  treat_missing_data  = "missing"
  alarm_actions       = [aws_sns_topic.p2_platform_ops.arn]
  ok_actions          = [aws_sns_topic.p2_platform_ops.arn]

  metric_name = "OpenCypherRequestsLatency"
  namespace   = "ApexMotion/Neptune"
  period      = 60
  statistic   = "Average"

  dimensions = {
    Cluster     = "apexmotion-neptune-cluster"
    Environment = var.environment
  }

  tags = {
    Environment = var.environment
    Component   = "neptune-graph"
    Severity    = "P2-High"
  }
}

# ------------------------------------------------------------------------------
# 6. Critical P0 Alarm: Deterministic Math Verification Mismatch
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "deterministic_math_mismatch" {
  alarm_name          = "apexmotion-${var.environment}-deterministic-math-mismatch"
  alarm_description   = "P0 Critical: Triggers emergency halt of mitigation drafting pipeline if deterministic math verification fails (LLD Sec 8.3)."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  datapoints_to_alarm = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.p1_pagerduty.arn]
  ok_actions          = [aws_sns_topic.p1_pagerduty.arn]

  metric_name = "CalculationHashVerificationFailure"
  namespace   = "ApexMotion/Platform"
  period      = 60
  statistic   = "Sum"

  dimensions = {
    Service     = "risk-calculator"
    Environment = var.environment
  }

  tags = {
    Environment = var.environment
    Component   = "deterministic-risk-engine"
    Severity    = "P0-Emergency"
  }
}

# ------------------------------------------------------------------------------
# 7. Medium Severity: Dead Letter Queue (DLQ) Accumulation (> 50 events)
# ------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "dlq_event_accumulation" {
  alarm_name          = "apexmotion-${var.environment}-dlq-accumulation"
  alarm_description   = "Medium Severity: DLQ depth exceeds 50 rejected events (FRD FMEA-04)."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 50
  datapoints_to_alarm = 2
  treat_missing_data  = "missing"
  alarm_actions       = [aws_sns_topic.p2_platform_ops.arn]
  ok_actions          = [aws_sns_topic.p2_platform_ops.arn]

  metric_name = "DeadLetterQueueDepth"
  namespace   = "ApexMotion/Kafka"
  period      = 60
  statistic   = "Maximum"

  dimensions = {
    Topic       = "dlq.operational.events"
    Environment = var.environment
  }

  tags = {
    Environment = var.environment
    Component   = "kafka-dlq"
    Severity    = "P3-Medium"
  }
}
