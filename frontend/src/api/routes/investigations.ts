/**
 * Multi-Agent Investigation API Routes (P12-1)
 *
 * Implements client functions for:
 * - POST /api/v1/investigations/start
 * - GET /api/v1/investigations/{id}
 * - GET /api/v1/cases/{case_id}
 */

import { apiGet, apiPost } from '../client';
import {
  type InvestigationDetailResponse,
  InvestigationDetailResponseSchema,
  type InvestigationStartRequest,
  type InvestigationStartResponse,
  InvestigationStartResponseSchema,
} from '../types';

export const startInvestigation = async (
  payload: InvestigationStartRequest
): Promise<InvestigationStartResponse> => {
  const data = await apiPost<unknown>('/api/v1/investigations/start', payload);
  return InvestigationStartResponseSchema.parse(data);
};

export const getInvestigation = async (
  investigationId: string
): Promise<InvestigationDetailResponse> => {
  const data = await apiGet<unknown>(
    `/api/v1/investigations/${encodeURIComponent(investigationId)}`
  );
  return InvestigationDetailResponseSchema.parse(data);
};

export const getCase = async (
  caseId: string
): Promise<InvestigationDetailResponse> => {
  const data = await apiGet<unknown>(
    `/api/v1/cases/${encodeURIComponent(caseId)}`
  );
  return InvestigationDetailResponseSchema.parse(data);
};

export const investigationApi = {
  startInvestigation,
  getInvestigation,
  getCase,
};
