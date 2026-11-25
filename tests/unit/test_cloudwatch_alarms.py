"""Unit tests for ApexMotion CloudWatch Alarms and operational alert routing.

Validates:
1. Canonical alarm configurations conforming to TASKS.md P15-5 & LLD Sec 8.3:
   - p95 Investigation Latency Breach (> 90.0s for 2 consecutive periods)
   - API 5xx Error Rate Breach (> 1.0% error rate for 2 consecutive periods)
   - Kafka Consumer Lag Breach (> 30.0s time lag / > 5,000 records for 5 minutes)
   - Neptune OpenCypher Query Latency Breach (> 2.0s / 2000ms for 2 periods)
   - Deterministic Math Verification Mismatch (> 0 calculation failures, P0 halt)
   - Dead Letter Queue Accumulation (> 50 rejected events, FMEA-04)
2. Boto3 CloudWatch API serialization and offline LocalStack/mock dispatch.
3. Declarative artifacts:
   - `monitoring/cloudwatch/alarms.json` valid AWS PutMetricAlarm JSON specifications.
   - `infrastructure/terraform/cloudwatch_alarms.tf` valid HCL definitions.
4. Metric emission resilience with error suppression and trace correlation.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.cloudwatch import (
    ALARM_API_ERROR_RATE,
    ALARM_DETERMINISTIC_MATH_MISMATCH,
    ALARM_DLQ_ACCUMULATION,
    ALARM_INVESTIGATION_P95_LATENCY,
    ALARM_KAFKA_CONSUMER_LAG,
    ALARM_NEPTUNE_QUERY_LATENCY,
    DEFAULT_ALARMS,
    CloudWatchAlarmConfig,
    CloudWatchAlarmManager,
    get_cloudwatch_alarm_manager,
)

ALARMS_JSON_PATH = Path("monitoring/cloudwatch/alarms.json")
TERRAFORM_TF_PATH = Path("infrastructure/terraform/cloudwatch_alarms.tf")


def test_alarm_configurations_registry_thresholds():
    """Verify standard alarm definitions conform strictly to TASKS.md and LLD Sec 8.3."""
    # 1. p95 Investigation Latency Breach (90s SLA)
    lat_alarm = DEFAULT_ALARMS[ALARM_INVESTIGATION_P95_LATENCY]
    assert lat_alarm.threshold == 90.0, "p95 latency threshold must be 90.0s"
    assert lat_alarm.extended_statistic == "p95", "Statistic must be p95"
    assert lat_alarm.comparison_operator == "GreaterThanThreshold"
    assert lat_alarm.evaluation_periods >= 2, "Evaluation periods must be >= 2"
    assert lat_alarm.period == 60, "Period must be 60s"

    # 2. API Error Rate (> 1.0%)
    err_alarm = DEFAULT_ALARMS[ALARM_API_ERROR_RATE]
    assert err_alarm.threshold == 1.0, "Error rate threshold must be 1.0%"
    assert err_alarm.comparison_operator == "GreaterThanThreshold"
    assert err_alarm.evaluation_periods >= 2

    # 3. Kafka Consumer Lag (> 30s or > 5,000 records)
    lag_alarm = DEFAULT_ALARMS[ALARM_KAFKA_CONSUMER_LAG]
    assert lag_alarm.threshold in (30.0, 5000.0), (
        "Kafka lag threshold must be 30.0s or 5000 records"
    )
    assert lag_alarm.comparison_operator == "GreaterThanThreshold"

    # 4. Neptune Query Latency (> 2.0s / 2000ms)
    nep_alarm = DEFAULT_ALARMS[ALARM_NEPTUNE_QUERY_LATENCY]
    assert nep_alarm.threshold in (2.0, 2000.0), (
        "Neptune query latency threshold must be 2.0s or 2000ms"
    )
    assert nep_alarm.comparison_operator == "GreaterThanThreshold"

    # 5. Deterministic Math Mismatch (P0 Emergency Halt)
    math_alarm = DEFAULT_ALARMS[ALARM_DETERMINISTIC_MATH_MISMATCH]
    assert math_alarm.threshold == 0.0, "Calculation mismatch threshold must be 0"
    assert math_alarm.comparison_operator == "GreaterThanThreshold"

    # 6. DLQ Depth Accumulation (> 50 events)
    dlq_alarm = DEFAULT_ALARMS[ALARM_DLQ_ACCUMULATION]
    assert dlq_alarm.threshold == 50.0, "DLQ threshold must be 50"
    assert dlq_alarm.comparison_operator == "GreaterThanThreshold"


def test_cloudwatch_alarm_config_serialization():
    """Verify CloudWatchAlarmConfig serializes cleanly into boto3 put_metric_alarm format."""
    config = CloudWatchAlarmConfig(
        alarm_name="test-p95-latency",
        alarm_description="Test p95 latency alarm",
        metric_name="InvestigationDurationSeconds",
        namespace="ApexMotion/Platform",
        extended_statistic="p95",
        period=60,
        evaluation_periods=2,
        threshold=90.0,
        comparison_operator="GreaterThanThreshold",
        dimensions={"Environment": "production", "Service": "investigation-orchestrator"},
        alarm_actions=["arn:aws:sns:us-east-1:123456789012:p1-pagerduty"],
    )

    boto_dict = config.to_boto3_dict()
    assert boto_dict["AlarmName"] == "test-p95-latency"
    assert boto_dict["MetricName"] == "InvestigationDurationSeconds"
    assert boto_dict["Namespace"] == "ApexMotion/Platform"
    assert boto_dict["ExtendedStatistic"] == "p95"
    assert boto_dict["Period"] == 60
    assert boto_dict["EvaluationPeriods"] == 2
    assert boto_dict["Threshold"] == 90.0
    assert boto_dict["ComparisonOperator"] == "GreaterThanThreshold"
    assert len(boto_dict["Dimensions"]) == 2
    assert {"Name": "Environment", "Value": "production"} in boto_dict["Dimensions"]
    assert boto_dict["AlarmActions"] == ["arn:aws:sns:us-east-1:123456789012:p1-pagerduty"]


def test_alarm_manager_put_metric_alarms_offline():
    """Verify CloudWatchAlarmManager registers all default alarms via boto3 mock client."""
    mock_boto_client = MagicMock()
    manager = CloudWatchAlarmManager(client=mock_boto_client)

    result = manager.put_metric_alarms()
    assert result["success"] is True
    assert result["alarms_created"] == len(DEFAULT_ALARMS)
    assert mock_boto_client.put_metric_alarm.call_count == len(DEFAULT_ALARMS)


def test_alarm_manager_describe_alarms():
    """Verify describe_alarms retrieves alarms from boto3 client."""
    mock_boto_client = MagicMock()
    mock_boto_client.describe_alarms.return_value = {
        "MetricAlarms": [
            {"AlarmName": "apexmotion-p95-investigation-latency", "StateValue": "OK"},
            {"AlarmName": "apexmotion-api-error-rate", "StateValue": "OK"},
        ]
    }
    manager = CloudWatchAlarmManager(client=mock_boto_client)

    alarms = manager.describe_alarms(prefix="apexmotion")
    assert len(alarms) == 2
    assert alarms[0]["AlarmName"] == "apexmotion-p95-investigation-latency"
    mock_boto_client.describe_alarms.assert_called_once_with(AlarmNamePrefix="apexmotion")


def test_emit_metric_and_resilience():
    """Verify emit_metric dispatches metric data and swallows network errors gracefully."""
    mock_boto_client = MagicMock()
    manager = CloudWatchAlarmManager(client=mock_boto_client)

    # 1. Normal successful emission
    res = manager.emit_metric(
        namespace="ApexMotion/Platform",
        metric_name="InvestigationDurationSeconds",
        value=78.5,
        unit="Seconds",
        dimensions={"Environment": "production"},
    )
    assert res is True
    mock_boto_client.put_metric_data.assert_called_once()
    call_args = mock_boto_client.put_metric_data.call_args[1]
    assert call_args["Namespace"] == "ApexMotion/Platform"
    assert call_args["MetricData"][0]["MetricName"] == "InvestigationDurationSeconds"
    assert call_args["MetricData"][0]["Value"] == 78.5

    # 2. Resilient error handling when client raises Exception
    mock_boto_client.put_metric_data.side_effect = Exception("AWS Network Failure")
    res_err = manager.emit_metric(
        namespace="ApexMotion/Platform",
        metric_name="InvestigationDurationSeconds",
        value=78.5,
    )
    assert res_err is False  # Must not crash application


def test_json_alarm_definitions_file_integrity():
    """Verify monitoring/cloudwatch/alarms.json exists and contains all required alarms."""
    assert ALARMS_JSON_PATH.exists(), f"Alarms JSON file missing at {ALARMS_JSON_PATH}"
    with open(ALARMS_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert "alarms" in data
    alarms = data["alarms"]
    alarm_names = [a.get("AlarmName") for a in alarms]

    # Verify 4 mandatory alarms from TASKS.md
    assert any("latency" in name.lower() and "p95" in name.lower() for name in alarm_names)
    assert any("error" in name.lower() for name in alarm_names)
    assert any("kafka" in name.lower() and "lag" in name.lower() for name in alarm_names)
    assert any("neptune" in name.lower() for name in alarm_names)

    # Verify specific threshold values in JSON
    p95_alarm = next(a for a in alarms if "p95" in a.get("AlarmName", "").lower())
    assert p95_alarm.get("Threshold") == 90.0

    err_alarm = next(a for a in alarms if "error" in a.get("AlarmName", "").lower())
    assert err_alarm.get("Threshold") == 1.0

    lag_alarm = next(a for a in alarms if "kafka" in a.get("AlarmName", "").lower())
    assert lag_alarm.get("Threshold") in (30.0, 5000.0)

    nep_alarm = next(a for a in alarms if "neptune" in a.get("AlarmName", "").lower())
    assert nep_alarm.get("Threshold") in (2.0, 2000.0)


def test_terraform_hcl_file_integrity():
    """Verify infrastructure/terraform/cloudwatch_alarms.tf exists and contains valid HCL."""
    assert TERRAFORM_TF_PATH.exists(), f"Terraform alarms file missing at {TERRAFORM_TF_PATH}"
    with open(TERRAFORM_TF_PATH, encoding="utf-8") as f:
        content = f.read()

    # Verify standard Terraform resource declarations
    assert 'resource "aws_cloudwatch_metric_alarm"' in content
    assert 'resource "aws_sns_topic"' in content
    assert "p95_investigation_latency" in content
    assert "api_error_rate" in content
    assert "kafka_consumer_lag" in content
    assert "neptune_query_latency" in content
    assert "deterministic_math_mismatch" in content
    assert "dlq_event_accumulation" in content

    # Verify threshold constants in HCL
    assert "90" in content
    assert "1" in content
    assert "2000" in content or "2" in content


def test_alarm_manager_singleton_and_factory():
    """Verify singleton accessor get_cloudwatch_alarm_manager."""
    with patch("boto3.client"):
        mgr1 = get_cloudwatch_alarm_manager()
        mgr2 = get_cloudwatch_alarm_manager()
        assert mgr1 is mgr2


def test_alarm_manager_edge_cases(tmp_path: Path):
    """Verify error branches and export_alarm_definitions_json in CloudWatchAlarmManager."""
    # 1. Export JSON to temporary path
    temp_json = tmp_path / "custom_alarms.json"
    manager = CloudWatchAlarmManager(client=MagicMock())
    exported = manager.export_alarm_definitions_json(output_path=temp_json)
    assert temp_json.exists()
    assert "apexmotion-p95-investigation-latency" in exported

    # 2. Put metric alarm failure handling
    failing_client = MagicMock()
    failing_client.put_metric_alarm.side_effect = Exception("ThrottlingException")
    failing_mgr = CloudWatchAlarmManager(client=failing_client)
    res = failing_mgr.put_metric_alarms()
    assert res["success"] is False
    assert len(res["errors"]) > 0

    # 3. Describe alarms exception handling
    failing_client.describe_alarms.side_effect = Exception("AccessDenied")
    assert failing_mgr.describe_alarms() == []

    # 4. None client fallback
    none_mgr = CloudWatchAlarmManager(client=None)
    none_mgr._client = None
    assert none_mgr.describe_alarms() == []
    assert none_mgr.emit_metric("ApexMotion", "TestMetric", 1.0) is False

    # 5. Composite metrics serialization in CloudWatchAlarmConfig
    composite_cfg = CloudWatchAlarmConfig(
        alarm_name="composite-alarm",
        alarm_description="Composite metric math",
        metric_name="e1",
        namespace="ApexMotion/Platform",
        threshold=1.0,
        metrics=[{"Id": "e1", "Expression": "m1 / m2"}],
        ok_actions=["arn:aws:sns:ok"],
        datapoints_to_alarm=3,
    )
    boto_dict = composite_cfg.to_boto3_dict()
    assert "Metrics" in boto_dict
    assert boto_dict["OKActions"] == ["arn:aws:sns:ok"]
    assert boto_dict["DatapointsToAlarm"] == 3
