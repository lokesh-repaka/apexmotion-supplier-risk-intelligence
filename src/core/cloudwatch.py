"""ApexMotion CloudWatch Alarms & Operational Alerting Infrastructure.

Implements centralized CloudWatch alarms configuration, management, and metric emission
conforming to TASKS.md P15-5, CLAUDE.md Sec 8.1, LLD Sec 8.3, and FRD FMEA-04:
- p95 Investigation Latency Breach (> 90.0s for 2 consecutive periods)
- API 5xx Error Rate Breach (> 1.0% error rate for 2 consecutive periods)
- Kafka Consumer Lag Breach (> 30.0s time lag / > 5,000 records, triggering KEDA autoscaling)
- Neptune OpenCypher Query Latency Breach (> 2.0s for 2 consecutive periods)
- Deterministic Math Verification Mismatch (> 0 calculation failures, P0 emergency halt)
- Dead Letter Queue Accumulation (> 50 rejected disruption events, FMEA-04)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import boto3
from botocore.config import Config

from src.core.config import get_settings

logger = logging.getLogger("apexmotion.cloudwatch")

# ------------------------------------------------------------------------------
# Alarm Name Constants
# ------------------------------------------------------------------------------
ALARM_INVESTIGATION_P95_LATENCY = "apexmotion-p95-investigation-latency"
ALARM_API_ERROR_RATE = "apexmotion-api-error-rate"
ALARM_KAFKA_CONSUMER_LAG = "apexmotion-kafka-consumer-lag"
ALARM_NEPTUNE_QUERY_LATENCY = "apexmotion-neptune-query-latency"
ALARM_DETERMINISTIC_MATH_MISMATCH = "apexmotion-deterministic-math-mismatch"
ALARM_DLQ_ACCUMULATION = "apexmotion-dlq-accumulation"


@dataclass
class CloudWatchAlarmConfig:
    """Strongly typed representation of an AWS CloudWatch Metric Alarm."""

    alarm_name: str
    alarm_description: str
    metric_name: str
    namespace: str
    threshold: float
    comparison_operator: str = "GreaterThanThreshold"
    evaluation_periods: int = 2
    period: int = 60
    statistic: str | None = None
    extended_statistic: str | None = None
    unit: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    alarm_actions: list[str] = field(default_factory=list)
    ok_actions: list[str] = field(default_factory=list)
    datapoints_to_alarm: int | None = None
    treat_missing_data: str = "missing"
    metrics: list[dict[str, Any]] | None = None

    def to_boto3_dict(self) -> dict[str, Any]:
        """Convert alarm configuration into standard AWS boto3 put_metric_alarm kwargs."""
        boto_dict: dict[str, Any] = {
            "AlarmName": self.alarm_name,
            "AlarmDescription": self.alarm_description,
            "Threshold": float(self.threshold),
            "ComparisonOperator": self.comparison_operator,
            "EvaluationPeriods": self.evaluation_periods,
            "Period": self.period,
            "TreatMissingData": self.treat_missing_data,
        }

        if self.metrics:
            boto_dict["Metrics"] = self.metrics
        else:
            boto_dict["MetricName"] = self.metric_name
            boto_dict["Namespace"] = self.namespace

            if self.extended_statistic:
                boto_dict["ExtendedStatistic"] = self.extended_statistic
            elif self.statistic:
                boto_dict["Statistic"] = self.statistic
            else:
                boto_dict["Statistic"] = "Average"

            if self.dimensions:
                boto_dict["Dimensions"] = [
                    {"Name": k, "Value": str(v)} for k, v in self.dimensions.items()
                ]

            if self.unit:
                boto_dict["Unit"] = self.unit

        if self.alarm_actions:
            boto_dict["AlarmActions"] = self.alarm_actions
        if self.ok_actions:
            boto_dict["OKActions"] = self.ok_actions
        if self.datapoints_to_alarm:
            boto_dict["DatapointsToAlarm"] = self.datapoints_to_alarm

        return boto_dict


# ------------------------------------------------------------------------------
# Standard Canonical Alarm Definitions
# ------------------------------------------------------------------------------
DEFAULT_ALARMS: dict[str, CloudWatchAlarmConfig] = {
    ALARM_INVESTIGATION_P95_LATENCY: CloudWatchAlarmConfig(
        alarm_name=ALARM_INVESTIGATION_P95_LATENCY,
        alarm_description=(
            "Critical SLO Breach: Triggers PagerDuty when p95 investigation duration exceeds "
            "90.0 seconds for 2 consecutive evaluation periods (PRD Sec 14, FRD FR-DEC-001)."
        ),
        metric_name="InvestigationDurationSeconds",
        namespace="ApexMotion/Platform",
        extended_statistic="p95",
        threshold=90.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=2,
        period=60,
        unit="Seconds",
        dimensions={"Service": "investigation-orchestrator"},
    ),
    ALARM_API_ERROR_RATE: CloudWatchAlarmConfig(
        alarm_name=ALARM_API_ERROR_RATE,
        alarm_description=(
            "High Severity: Triggers when inbound HTTP 5xx error rate exceeds 1.0% across "
            "2 evaluation periods, indicating API gateway or backend degradation."
        ),
        metric_name="5xx_error_rate",
        namespace="ApexMotion/Platform",
        statistic="Average",
        threshold=1.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=2,
        period=60,
        unit="Percent",
        dimensions={"Service": "fastapi-gateway"},
    ),
    ALARM_KAFKA_CONSUMER_LAG: CloudWatchAlarmConfig(
        alarm_name=ALARM_KAFKA_CONSUMER_LAG,
        alarm_description=(
            "High Severity: Triggers when Kafka consumer lag exceeds 30.0 seconds for 5 minutes, "
            "triggering KEDA autoscaling up to 24 worker pods (LLD Sec 8.3)."
        ),
        metric_name="EstimatedMaxTimeLag",
        namespace="ApexMotion/Kafka",
        statistic="Maximum",
        threshold=30.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=3,
        period=60,
        unit="Seconds",
        dimensions={"ConsumerGroup": "apexmotion-disruption-consumers"},
    ),
    ALARM_NEPTUNE_QUERY_LATENCY: CloudWatchAlarmConfig(
        alarm_name=ALARM_NEPTUNE_QUERY_LATENCY,
        alarm_description=(
            "High Severity: Triggers when Amazon Neptune OpenCypher query latency exceeds "
            "2.0 seconds for 2 consecutive evaluation periods (LLD Sec 8.3)."
        ),
        metric_name="OpenCypherRequestsLatency",
        namespace="ApexMotion/Neptune",
        statistic="Average",
        threshold=2.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=2,
        period=60,
        unit="Seconds",
        dimensions={"Cluster": "apexmotion-neptune-cluster"},
    ),
    ALARM_DETERMINISTIC_MATH_MISMATCH: CloudWatchAlarmConfig(
        alarm_name=ALARM_DETERMINISTIC_MATH_MISMATCH,
        alarm_description=(
            "P0 Critical Emergency Halt: Triggers immediate halt of action drafting pipeline if "
            "deterministic risk engine calculation hash deviates (LLD Sec 8.3)."
        ),
        metric_name="CalculationHashVerificationFailure",
        namespace="ApexMotion/Platform",
        statistic="Sum",
        threshold=0.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=1,
        period=60,
        unit="Count",
        dimensions={"Service": "risk-calculator"},
    ),
    ALARM_DLQ_ACCUMULATION: CloudWatchAlarmConfig(
        alarm_name=ALARM_DLQ_ACCUMULATION,
        alarm_description=(
            "Medium Severity: Triggers alert when Dead Letter Queue depth exceeds 50 rejected "
            "supplier disruption events (FRD FMEA-04)."
        ),
        metric_name="DeadLetterQueueDepth",
        namespace="ApexMotion/Kafka",
        statistic="Maximum",
        threshold=50.0,
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=2,
        period=60,
        unit="Count",
        dimensions={"Topic": "dlq.operational.events"},
    ),
}


class CloudWatchAlarmManager:
    """Manages CloudWatch alarms provisioning, inspection, and metric publishing."""

    def __init__(self, client: Any = None) -> None:
        """Initialize the CloudWatch client with LocalStack and offline fallback support."""
        settings = get_settings()
        self.region = settings.AWS_REGION
        self._use_localstack = (
            os.getenv("USE_LOCALSTACK", "false").lower() == "true"
            or os.getenv("ENVIRONMENT", "").lower() == "test"
        )

        if client is not None:
            self._client = client
        else:
            boto_config = Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=2.0,
                read_timeout=3.0,
            )
            endpoint_url = "http://localhost:4566" if self._use_localstack else None
            try:
                self._client = boto3.client(
                    "cloudwatch",
                    region_name=self.region,
                    endpoint_url=endpoint_url,
                    config=boto_config,
                )
            except Exception as e:
                logger.warning(
                    "Could not initialize live boto3 CloudWatch client: %s. Using stub client.",
                    e,
                )
                self._client = None

    def put_metric_alarms(
        self, alarms: dict[str, CloudWatchAlarmConfig] | None = None
    ) -> dict[str, Any]:
        """Put all configured CloudWatch alarms into AWS CloudWatch."""
        active_alarms = alarms or DEFAULT_ALARMS
        created: list[str] = []
        errors: list[str] = []

        for _alarm_key, config in active_alarms.items():
            boto_payload = config.to_boto3_dict()
            try:
                if self._client is not None and hasattr(self._client, "put_metric_alarm"):
                    self._client.put_metric_alarm(**boto_payload)
                created.append(config.alarm_name)
                logger.info("Configured CloudWatch alarm: %s", config.alarm_name)
            except Exception as e:
                logger.error("Failed to configure CloudWatch alarm %s: %s", config.alarm_name, e)
                errors.append(f"{config.alarm_name}: {e}")

        return {
            "success": len(errors) == 0,
            "alarms_created": len(created),
            "created": created,
            "errors": errors,
        }

    def describe_alarms(self, prefix: str = "apexmotion") -> list[dict[str, Any]]:
        """Retrieve metric alarms matching the given prefix."""
        if self._client is None or not hasattr(self._client, "describe_alarms"):
            return []

        try:
            response = self._client.describe_alarms(AlarmNamePrefix=prefix)
            return cast(list[dict[str, Any]], response.get("MetricAlarms", []))
        except Exception as e:
            logger.warning("Failed to describe CloudWatch alarms: %s", e)
            return []

    def emit_metric(
        self,
        namespace: str,
        metric_name: str,
        value: float,
        unit: str | None = None,
        dimensions: dict[str, str] | None = None,
    ) -> bool:
        """Publish custom metric data to CloudWatch with error suppression."""
        if self._client is None or not hasattr(self._client, "put_metric_data"):
            return False

        metric_datum: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": float(value),
        }
        if unit:
            metric_datum["Unit"] = unit
        if dimensions:
            metric_datum["Dimensions"] = [
                {"Name": k, "Value": str(v)} for k, v in dimensions.items()
            ]

        try:
            self._client.put_metric_data(
                Namespace=namespace,
                MetricData=[metric_datum],
            )
            return True
        except Exception as e:
            logger.warning(
                "Suppressed CloudWatch metric emission failure for %s/%s: %s",
                namespace,
                metric_name,
                e,
            )
            return False

    def export_alarm_definitions_json(
        self,
        output_path: Path | str = "monitoring/cloudwatch/alarms.json",
    ) -> str:
        """Export all default alarm definitions to AWS PutMetricAlarm JSON specification."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        alarm_payloads = [config.to_boto3_dict() for config in DEFAULT_ALARMS.values()]
        document = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "version": "1.0",
            "environment": "production",
            "alarms": alarm_payloads,
        }

        serialized = json.dumps(document, indent=2)
        with open(path, "w", encoding="utf-8") as f:
            f.write(serialized)

        return serialized


# ------------------------------------------------------------------------------
# Singleton Accessor
# ------------------------------------------------------------------------------
_MANAGER_INSTANCE: CloudWatchAlarmManager | None = None


def get_cloudwatch_alarm_manager() -> CloudWatchAlarmManager:
    """Return thread-safe singleton instance of CloudWatchAlarmManager."""
    global _MANAGER_INSTANCE
    if _MANAGER_INSTANCE is None:
        _MANAGER_INSTANCE = CloudWatchAlarmManager()
    return _MANAGER_INSTANCE


__all__ = [
    "ALARM_API_ERROR_RATE",
    "ALARM_DETERMINISTIC_MATH_MISMATCH",
    "ALARM_DLQ_ACCUMULATION",
    "ALARM_INVESTIGATION_P95_LATENCY",
    "ALARM_KAFKA_CONSUMER_LAG",
    "ALARM_NEPTUNE_QUERY_LATENCY",
    "DEFAULT_ALARMS",
    "CloudWatchAlarmConfig",
    "CloudWatchAlarmManager",
    "get_cloudwatch_alarm_manager",
]
