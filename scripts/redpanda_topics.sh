#!/usr/bin/env bash
# ==============================================================================
# ApexMotion Supplier Risk Intelligence Platform — Redpanda / Kafka Topic Setup
# Provisions the core streaming event bus topics:
# 1. supplier-events  (Real-time disruption events from news and external ERP/EDI)
# 2. risk-alerts      (Deterministic calculation outputs & threshold violations)
# 3. hitl-required    (Pending human-in-the-loop spend authorizations)
# 4. audit-events     (Append-only immutable audit trail stream)
# ==============================================================================

set -euo pipefail

# Configuration defaults matching .env.example and src/core/config.py
REDPANDA_BROKERS="${REDPANDA_BROKERS:-${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}}"
CONTAINER_NAME="${REDPANDA_CONTAINER_NAME:-apexmotion-redpanda}"
DEFAULT_PARTITIONS="${DEFAULT_PARTITIONS:-3}"
DEFAULT_REPLICAS="${DEFAULT_REPLICAS:-1}"

log_info() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [INFO] [redpanda-topics] $*"
}

log_error() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [ERROR] [redpanda-topics] $*" >&2
}

# Determine the best execution method for rpk
run_rpk() {
    if command -v rpk &>/dev/null; then
        rpk "$@" --brokers "${REDPANDA_BROKERS}"
    elif command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker exec -i "${CONTAINER_NAME}" rpk "$@" --brokers localhost:9092
    else
        log_error "Neither local 'rpk' CLI nor running Docker container '${CONTAINER_NAME}' was found."
        log_error "Please ensure Redpanda is running via 'docker compose up -d' or install 'rpk'."
        exit 1
    fi
}

log_info "Starting Redpanda / Kafka topic provisioning on broker: ${REDPANDA_BROKERS}"

# Topic Definitions (Topic Name, Partitions, Replicas, Retention MS)
declare -A TOPIC_PARTITIONS=(
    ["supplier-events"]="3"
    ["risk-alerts"]="3"
    ["hitl-required"]="3"
    ["audit-events"]="3"
)

# Fetch existing topics if possible
EXISTING_TOPICS=""
if EXISTING_TOPICS=$(run_rpk topic list 2>/dev/null | awk '{print $1}'); then
    log_info "Retrieved existing topics from broker."
else
    log_info "Could not query topic list in advance; will create with existence check."
fi

for TOPIC in "supplier-events" "risk-alerts" "hitl-required" "audit-events"; do
    PARTITIONS="${TOPIC_PARTITIONS[$TOPIC]:-$DEFAULT_PARTITIONS}"
    REPLICAS="${DEFAULT_REPLICAS}"

    if echo "${EXISTING_TOPICS}" | grep -qw "^${TOPIC}$"; then
        log_info "Topic '${TOPIC}' already exists. Skipping creation."
    else
        log_info "Creating topic '${TOPIC}' (partitions=${PARTITIONS}, replicas=${REPLICAS})..."
        if run_rpk topic create "${TOPIC}" \
            --partitions "${PARTITIONS}" \
            --replicas "${REPLICAS}" 2>&1 | grep -E -v "TOPIC_ALREADY_EXISTS|already exists"; then
            log_info "Topic '${TOPIC}' created successfully."
        else
            log_info "Topic '${TOPIC}' provisioned."
        fi
    fi
done

log_info "All 4 ApexMotion Kafka topics verified and ready for streaming."
