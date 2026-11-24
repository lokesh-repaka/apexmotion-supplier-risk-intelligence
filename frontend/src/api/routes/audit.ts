/**
 * Audit Trail API Routes (P12-6)
 *
 * Implements client functions for:
 * - GET /api/v1/alerts/{alert_id}/audit (Chronological immutable forensic audit trail per alert)
 */

import { apiGet } from '../client';
import {
  type AuditLogListResponse,
  AuditLogListResponseSchema,
} from '../types';

export const getAlertAuditTrail = async (
  alertId: string
): Promise<AuditLogListResponse> => {
  const data = await apiGet<unknown>(
    `/api/v1/alerts/${encodeURIComponent(alertId)}/audit`
  );
  return AuditLogListResponseSchema.parse(data);
};

export const auditApi = {
  getAlertAuditTrail,
};
