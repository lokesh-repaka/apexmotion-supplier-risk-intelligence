/**
 * Supplier Intelligence API Routes (P12-1)
 *
 * Implements client functions for:
 * - GET /api/v1/suppliers
 * - GET /api/v1/suppliers/{id}
 * - GET /api/v1/suppliers/{id}/risk
 * - GET /api/v1/suppliers/{id}/graph
 */

import { apiGet } from '../client';
import {
  type SupplierGraphResponse,
  SupplierGraphResponseSchema,
  type SupplierListParams,
  type SupplierListResponse,
  SupplierListResponseSchema,
  type SupplierResponse,
  SupplierSchema,
  type SupplierRisk,
  SupplierRiskResponseSchema,
} from '../types';

export const getSuppliers = async (
  params?: SupplierListParams
): Promise<SupplierListResponse> => {
  const data = await apiGet<unknown>('/api/v1/suppliers', { params });
  return SupplierListResponseSchema.parse(data);
};

export const getSupplier = async (supplierId: string): Promise<SupplierResponse> => {
  const data = await apiGet<unknown>(
    `/api/v1/suppliers/${encodeURIComponent(supplierId)}`
  );
  return SupplierSchema.parse(data);
};

export const getSupplierRisk = async (supplierId: string): Promise<SupplierRisk> => {
  const data = await apiGet<unknown>(
    `/api/v1/suppliers/${encodeURIComponent(supplierId)}/risk`
  );
  return SupplierRiskResponseSchema.parse(data);
};

export const getSupplierGraph = async (
  supplierId: string,
  maxDepth = 2
): Promise<SupplierGraphResponse> => {
  const data = await apiGet<unknown>(
    `/api/v1/suppliers/${encodeURIComponent(supplierId)}/graph`,
    { params: { max_depth: maxDepth } }
  );
  return SupplierGraphResponseSchema.parse(data);
};

export const supplierApi = {
  getSuppliers,
  getSupplier,
  getSupplierRisk,
  getSupplierGraph,
};
