#!/usr/bin/env bash
# ==============================================================================
# ApexMotion Supplier Risk Intelligence Platform - Blue-Green Cutover Automation
# Automates zero-downtime service selector cutover with pre-flight health checks
# and automated rollback traps.
# Reference: TASKS.md (P16-5) & CLAUDE.md Sec 15
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Configuration & Defaults
# ------------------------------------------------------------------------------
NAMESPACE="${NAMESPACE:-apexmotion}"
SERVICE_NAME="${SERVICE_NAME:-apexmotion-api}"
TARGET_COLOR="${TARGET_COLOR:-green}"
ACTIVE_COLOR="${ACTIVE_COLOR:-blue}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-60}"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-5}"
HEALTH_ENDPOINT="${HEALTH_ENDPOINT:-/health}"

echo "========================================================================"
echo " ApexMotion Blue-Green Service Cutover Automation"
echo " Target Namespace: ${NAMESPACE}"
echo " Service Name:     ${SERVICE_NAME}"
echo " Current Active:   ${ACTIVE_COLOR}"
echo " Target Revision:  ${TARGET_COLOR}"
echo "========================================================================"

# Validate target color
if [[ "${TARGET_COLOR}" != "blue" && "${TARGET_COLOR}" != "green" ]]; then
    echo "ERROR: TARGET_COLOR must be either 'blue' or 'green' (got '${TARGET_COLOR}')" >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# Rollback Trap Handler
# ------------------------------------------------------------------------------
rollback() {
    local exit_code=$?
    if [[ ${exit_code} -ne 0 ]]; then
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
        echo " CRITICAL FAILURE DETECTED (Exit code: ${exit_code})" >&2
        echo " Executing automated emergency rollback to ${ACTIVE_COLOR}..." >&2
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2

        kubectl patch service "${SERVICE_NAME}" -n "${NAMESPACE}" \
            -p "{\"spec\":{\"selector\":{\"app\":\"apexmotion-api\",\"deployment_color\":\"${ACTIVE_COLOR}\"}}}" || true

        echo "Emergency rollback to ${ACTIVE_COLOR} completed." >&2
    fi
}
trap rollback EXIT

# ------------------------------------------------------------------------------
# Pre-Flight Health Check: Verify Target Revision Health Before Cutover
# ------------------------------------------------------------------------------
echo "==> Step 1: Running pre-flight health checks on target deployment (${TARGET_COLOR})..."

TARGET_DEPLOYMENT="apexmotion-api-${TARGET_COLOR}"
echo "Verifying rollout status for ${TARGET_DEPLOYMENT}..."
kubectl rollout status deployment/"${TARGET_DEPLOYMENT}" -n "${NAMESPACE}" --timeout="${HEALTH_TIMEOUT_SECONDS}s"

echo "Probing container health endpoint for target deployment..."
elapsed=0
healthy=0

while [[ ${elapsed} -lt ${HEALTH_TIMEOUT_SECONDS} ]]; do
    # Probe pod IP or service health via kubectl exec or port-forward proxy
    if kubectl run "healthcheck-probe-${TARGET_COLOR}-$RANDOM" --rm -i --restart=Never \
        --namespace="${NAMESPACE}" \
        --image="curlimages/curl:8.7.1" \
        --command -- curl -sf "http://${TARGET_DEPLOYMENT}.${NAMESPACE}.svc.cluster.local:8000${HEALTH_ENDPOINT}" > /dev/null 2>&1; then
        healthy=1
        echo "Target deployment ${TARGET_DEPLOYMENT} is HEALTHY (HTTP 200 OK)."
        break
    else
        echo "Target not ready yet... waiting ${HEALTH_INTERVAL_SECONDS}s (${elapsed}/${HEALTH_TIMEOUT_SECONDS}s elapsed)"
        sleep "${HEALTH_INTERVAL_SECONDS}"
        elapsed=$((elapsed + HEALTH_INTERVAL_SECONDS))
    fi
done

if [[ ${healthy} -ne 1 ]]; then
    echo "ERROR: Target deployment ${TARGET_DEPLOYMENT} failed health check within ${HEALTH_TIMEOUT_SECONDS}s." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# Atomic Service Selector Cutover
# ------------------------------------------------------------------------------
echo "==> Step 2: Executing atomic service selector cutover to ${TARGET_COLOR}..."

kubectl patch service "${SERVICE_NAME}" -n "${NAMESPACE}" \
    -p "{\"spec\":{\"selector\":{\"app\":\"apexmotion-api\",\"deployment_color\":\"${TARGET_COLOR}\"}}}"

echo "Service ${SERVICE_NAME} patched successfully."

# ------------------------------------------------------------------------------
# Post-Cutover Live Traffic Verification
# ------------------------------------------------------------------------------
echo "==> Step 3: Verifying live traffic routing on primary service ${SERVICE_NAME}..."
sleep 3

if kubectl run "post-cutover-probe-$RANDOM" --rm -i --restart=Never \
    --namespace="${NAMESPACE}" \
    --image="curlimages/curl:8.7.1" \
    --command -- curl -sf "http://${SERVICE_NAME}.${NAMESPACE}.svc.cluster.local:80${HEALTH_ENDPOINT}" > /dev/null 2>&1; then
    echo "Live service ${SERVICE_NAME} verified HEALTHY on ${TARGET_COLOR}."
else
    echo "ERROR: Live service verification failed post-cutover!" >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# Cutover Success: Disarm Trap & Clean Up
# ------------------------------------------------------------------------------
trap - EXIT

echo "========================================================================"
echo " Blue-Green Cutover SUCCESSFUL!"
echo " Primary Service '${SERVICE_NAME}' is now serving on '${TARGET_COLOR}'."
echo " Previous Active '${ACTIVE_COLOR}' can be retained for rollback or drained."
echo "========================================================================"
exit 0
