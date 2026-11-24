/**
 * HITL Spend Approval API Routes (P12-1)
 *
 * Implements client functions for:
 * - GET /api/v1/approvals (queue)
 * - GET /api/v1/approvals/{id}
 * - POST /api/v1/approvals/{id}/sign
 * - POST /api/v1/approvals/{id}/reject
 */

import { apiGet, apiPost } from '../client';
import {
  type ApprovalItem,
  ApprovalItemSchema,
  type ApprovalListParams,
  type ApprovalQueueListResponse,
  ApprovalQueueListResponseSchema,
  type ApprovalRejectRequest,
  type ApprovalSignRequest,
  type ApprovalSignResponse,
  ApprovalSignResponseSchema,
} from '../types';

export const getApprovals = async (
  params?: ApprovalListParams
): Promise<ApprovalQueueListResponse> => {
  const data = await apiGet<unknown>('/api/v1/approvals', { params });
  return ApprovalQueueListResponseSchema.parse(data);
};

export const getApproval = async (approvalId: string): Promise<ApprovalItem> => {
  const data = await apiGet<unknown>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}`
  );
  return ApprovalItemSchema.parse(data);
};

export const signApproval = async (
  approvalId: string,
  payload: ApprovalSignRequest
): Promise<ApprovalSignResponse> => {
  const data = await apiPost<unknown>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/sign`,
    payload
  );
  return ApprovalSignResponseSchema.parse(data);
};

export const rejectApproval = async (
  approvalId: string,
  payload: ApprovalRejectRequest
): Promise<ApprovalItem> => {
  const data = await apiPost<unknown>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/reject`,
    payload
  );
  return ApprovalItemSchema.parse(data);
};

export const approvalApi = {
  getApprovals,
  getApproval,
  signApproval,
  rejectApproval,
};
