/**
 * Risk & Alert API Routes (P12-1)
 *
 * Implements client functions for:
 * - POST /api/v1/risk/evaluate
 * - GET /api/v1/alerts
 * - GET /api/v1/alerts/{id}
 * - POST /api/v1/alerts/{id}/acknowledge
 */

import { apiGet, apiPost } from '../client';
import {
  type AlertAcknowledgeRequest,
  type AlertAcknowledgeResponse,
  AlertAcknowledgeResponseSchema,
  type RiskAlert,
  type RiskAlertListParams,
  type RiskAlertListResponse,
  RiskAlertListResponseSchema,
  RiskAlertSchema,
  type RiskEvaluationRequest,
  type RiskEvaluationResponse,
  RiskEvaluationResponseSchema,
} from '../types';

export const evaluateRisk = async (
  payload: RiskEvaluationRequest
): Promise<RiskEvaluationResponse> => {
  const data = await apiPost<unknown>('/api/v1/risk/evaluate', payload);
  return RiskEvaluationResponseSchema.parse(data);
};

export const getAlerts = async (
  params?: RiskAlertListParams
): Promise<RiskAlertListResponse> => {
  const data = await apiGet<unknown>('/api/v1/alerts', { params });
  return RiskAlertListResponseSchema.parse(data);
};

export const getAlert = async (alertId: string): Promise<RiskAlert> => {
  const data = await apiGet<unknown>(`/api/v1/alerts/${encodeURIComponent(alertId)}`);
  return RiskAlertSchema.parse(data);
};

export const acknowledgeAlert = async (
  alertId: string,
  payload?: AlertAcknowledgeRequest
): Promise<AlertAcknowledgeResponse> => {
  const data = await apiPost<unknown>(
    `/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    payload ?? {}
  );
  return AlertAcknowledgeResponseSchema.parse(data);
};

export const riskApi = {
  evaluateRisk,
  getAlerts,
  getAlert,
  acknowledgeAlert,
};
