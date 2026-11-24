/**
 * Frontend Typed API Schemas & Interfaces (P12-1)
 *
 * Implements Zod v3 schemas and TypeScript inferred types for all ApexMotion
 * backend routes, ensuring strict alignment with FastAPI Pydantic v2 models,
 * canonical error envelopes (CLAUDE.md Section 10), and BR-RULE-001 Decimal precision.
 */

import { z } from 'zod';

// =============================================================================
// 1. Canonical Error Envelopes (CLAUDE.md Section 10)
// =============================================================================

export const ApiErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  trace_id: z.string().default('unknown'),
  details: z.unknown().optional(),
});

export const ApiErrorEnvelopeSchema = z.object({
  error: ApiErrorDetailSchema,
});

export type ApiErrorDetail = z.infer<typeof ApiErrorDetailSchema>;
export type ApiErrorEnvelope = z.infer<typeof ApiErrorEnvelopeSchema>;

export class ApiError extends Error {
  readonly code: string;
  readonly traceId: string;
  readonly statusCode: number;
  readonly details?: unknown;

  constructor(
    message: string,
    code = 'INTERNAL_ERROR',
    traceId = 'unknown',
    statusCode = 500,
    details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.traceId = traceId;
    this.statusCode = statusCode;
    this.details = details;
  }
}

// =============================================================================
// 2. Pagination & Common Query Schemas
// =============================================================================

export const PaginationParamsSchema = z.object({
  page: z.number().int().min(1).optional().default(1),
  page_size: z.number().int().min(1).max(100).optional().default(20),
});

export type PaginationParams = z.input<typeof PaginationParamsSchema>;

// =============================================================================
// 3. Risk Evaluation & Alert Schemas (src/api/schemas/risk.py)
// =============================================================================

export const RiskLevelEnum = z.enum(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']);
export type RiskLevel = z.infer<typeof RiskLevelEnum>;

export const PipelineTrackEnum = z.enum(['FAST_TRACK', 'FULL_TRACK']);
export type PipelineTrack = z.infer<typeof PipelineTrackEnum>;

export const RiskEvaluationRequestSchema = z.object({
  component_sku: z.string().min(1).max(100),
  supplier_id: z.string().nullable().optional(),
  plant_id: z.string().nullable().optional(),
  current_stock: z.union([z.number(), z.string()]).nullable().optional(),
  daily_consumption_rate: z.union([z.number(), z.string()]).nullable().optional(),
  eta_days: z.union([z.number(), z.string()]).nullable().optional(),
  unit_cost_usd: z.union([z.number(), z.string()]).nullable().optional(),
  signal_type: z.string().optional().default('logistics'),
  severity_hint: z.string().nullable().optional(),
  disruption_description: z.string().max(2000).nullable().optional(),
  pipeline_mode: z.enum(['auto', 'fast_track', 'full_track']).optional().default('auto'),
});

export type RiskEvaluationRequest = z.input<typeof RiskEvaluationRequestSchema>;

export const RiskEvaluationResponseSchema = z.object({
  evaluation_id: z.string(),
  alert_id: z.string().nullable().optional(),
  pipeline_track: PipelineTrackEnum,
  status: z.string(),
  component_sku: z.string(),
  supplier_id: z.string().nullable().optional(),
  days_of_cover: z.union([z.number(), z.string()]).nullable().optional(),
  gap_days: z.union([z.number(), z.string()]).nullable().optional(),
  shortage_volume: z.number().nullable().optional(),
  financial_exposure_usd: z.union([z.number(), z.string()]).nullable().optional(),
  risk_level: RiskLevelEnum,
  requires_hitl: z.boolean(),
  governing_spend_tier: z.string().nullable().optional(),
  fast_track_reason: z.string().nullable().optional(),
  evaluated_at: z.string(),
});

export type RiskEvaluationResponse = z.infer<typeof RiskEvaluationResponseSchema>;

export const RiskAlertSchema = z.object({
  id: z.string(),
  supplier_id: z.string().nullable().optional(),
  component_sku: z.string(),
  risk_level: z.string(),
  days_of_cover: z.union([z.number(), z.string()]).nullable().optional(),
  financial_exposure: z.union([z.number(), z.string()]).nullable().optional(),
  shortage_volume: z.number().nullable().optional(),
  status: z.string(),
  created_at: z.string(),
});

export type RiskAlert = z.infer<typeof RiskAlertSchema>;

export const RiskAlertListResponseSchema = z.object({
  items: z.array(RiskAlertSchema),
  total: z.number().int().min(0),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
  total_pages: z.number().int().min(0),
});

export type RiskAlertListResponse = z.infer<typeof RiskAlertListResponseSchema>;

export const RiskAlertListParamsSchema = PaginationParamsSchema.extend({
  status: z.string().optional(),
  risk_level: z.string().optional(),
  supplier_id: z.string().optional(),
  component_sku: z.string().optional(),
});

export type RiskAlertListParams = z.input<typeof RiskAlertListParamsSchema>;

export const AlertAcknowledgeRequestSchema = z.object({
  notes: z.string().max(1000).nullable().optional(),
});

export type AlertAcknowledgeRequest = z.infer<typeof AlertAcknowledgeRequestSchema>;

export const AlertAcknowledgeResponseSchema = z.object({
  id: z.string(),
  status: z.literal('ACKNOWLEDGED'),
  acknowledged_by: z.string(),
  acknowledged_at: z.string(),
  notes: z.string().nullable().optional(),
});

export type AlertAcknowledgeResponse = z.infer<typeof AlertAcknowledgeResponseSchema>;

// =============================================================================
// 4. Investigation Schemas (src/api/schemas/investigation.py)
// =============================================================================

export const InvestigationStartRequestSchema = z.object({
  supplier_id: z.string().min(1),
  alert_id: z.string().nullable().optional(),
  component_sku: z.string().nullable().optional(),
  signal_type: z.string().optional().default('news'),
  raw_signal: z.string().optional().default(''),
  external_source_url: z.string().nullable().optional(),
  target_supplier_hint: z.string().nullable().optional(),
  severity_hint: z.string().nullable().optional(),
  current_stock: z.number().int().min(0).nullable().optional(),
  daily_consumption_rate: z.union([z.number(), z.string()]).nullable().optional(),
  eta_days: z.union([z.number(), z.string()]).nullable().optional(),
  unit_cost_usd: z.union([z.number(), z.string()]).nullable().optional(),
  metadata: z.record(z.unknown()).optional().default({}),
  wait_for_completion: z.boolean().optional().default(false),
});

export type InvestigationStartRequest = z.input<typeof InvestigationStartRequestSchema>;

export const InvestigationStartResponseSchema = z.object({
  investigation_id: z.string(),
  case_id: z.string(),
  alert_id: z.string().nullable().optional(),
  status: z.string().default('RUNNING'),
  poll_url: z.string(),
  started_at: z.string(),
  estimated_completion_seconds: z.number().int().optional().default(90),
  message: z.string().optional().default('Investigation pipeline started successfully'),
});

export type InvestigationStartResponse = z.infer<typeof InvestigationStartResponseSchema>;

export const InvestigationDetailResponseSchema = z.object({
  investigation_id: z.string(),
  case_id: z.string(),
  alert_id: z.string().nullable().optional(),
  supplier_id: z.string(),
  component_sku: z.string().nullable().optional(),
  status: z.string(),
  current_node: z.string().nullable().optional(),
  execution_path: z.array(z.string()).optional().default([]),
  risk_metrics: z.record(z.unknown()).nullable().optional(),
  severity: z.string().nullable().optional(),
  narrative: z.string().nullable().optional(),
  research_analysis: z.record(z.unknown()).nullable().optional(),
  contract_analysis: z.record(z.unknown()).nullable().optional(),
  recommendations: z.array(z.record(z.unknown())).nullable().optional(),
  recommended_action_id: z.string().nullable().optional(),
  requires_hitl: z.boolean().default(false),
  governing_spend_tier: z.string().nullable().optional(),
  errors: z.array(z.string()).optional().default([]),
  started_at: z.string(),
  completed_at: z.string().nullable().optional(),
  duration_ms: z.number().nullable().optional(),
  tokens_used: z.number().nullable().optional(),
  cost_usd: z.union([z.number(), z.string()]).nullable().optional(),
});

export type InvestigationDetailResponse = z.infer<typeof InvestigationDetailResponseSchema>;

// =============================================================================
// 5. HITL Approval Schemas (src/api/schemas/approval.py)
// =============================================================================

export const SpendTierEnum = z.enum(['CATEGORY_MGR', 'PROC_DIRECTOR', 'DUAL_VP']);
export type SpendTier = z.infer<typeof SpendTierEnum>;

export const ApprovalStatusEnum = z.enum([
  'PENDING',
  'PARTIALLY_APPROVED',
  'APPROVED',
  'REJECTED',
  'EXPIRED',
]);
export type ApprovalStatus = z.infer<typeof ApprovalStatusEnum>;

export const ApprovalItemSchema = z.object({
  id: z.string(),
  alert_id: z.string().nullable().optional(),
  action_type: z.string(),
  amount_usd: z.union([z.number(), z.string()]),
  spend_tier: z.string(),
  token_hash: z.string(),
  approved_by: z.array(z.string()).optional().default([]),
  approved_at: z.array(z.string()).optional().default([]),
  status: z.string(),
  expires_at: z.string(),
  created_at: z.string(),
});

export type ApprovalItem = z.infer<typeof ApprovalItemSchema>;

export const ApprovalQueueListResponseSchema = z.object({
  items: z.array(ApprovalItemSchema),
  total: z.number().int().min(0),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
  total_pages: z.number().int().min(0),
});

export type ApprovalQueueListResponse = z.infer<typeof ApprovalQueueListResponseSchema>;

export const ApprovalListParamsSchema = PaginationParamsSchema.extend({
  status: z.string().optional(),
  spend_tier: z.string().optional(),
});

export type ApprovalListParams = z.input<typeof ApprovalListParamsSchema>;

export const ApprovalSignRequestSchema = z.object({
  token: z.string().min(10).max(10000),
  notes: z.string().max(2000).nullable().optional(),
});

export type ApprovalSignRequest = z.infer<typeof ApprovalSignRequestSchema>;

export const ApprovalSignResponseSchema = z.object({
  id: z.string(),
  status: z.string(),
  action_type: z.string(),
  amount_usd: z.union([z.number(), z.string()]),
  spend_tier: z.string(),
  approved_by: z.array(z.string()).optional().default([]),
  approved_at: z.array(z.string()).optional().default([]),
  message: z.string().optional(),
});

export type ApprovalSignResponse = z.infer<typeof ApprovalSignResponseSchema>;

export const ApprovalRejectRequestSchema = z.object({
  justification: z.string().min(1).max(2000),
});

export type ApprovalRejectRequest = z.infer<typeof ApprovalRejectRequestSchema>;

// =============================================================================
// 6. Supplier Intelligence Schemas (src/api/schemas/supplier.py)
// =============================================================================

export const SupplierSchema = z.object({
  id: z.string(),
  name: z.string(),
  country_code: z.string(),
  tier: z.number().int().min(1).max(3),
  risk_score: z.union([z.number(), z.string()]).nullable().optional(),
  neptune_node_id: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Supplier = z.infer<typeof SupplierSchema>;
export type SupplierResponse = Supplier;

export const SupplierListResponseSchema = z.object({
  items: z.array(SupplierSchema),
  total: z.number().int().min(0),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
  total_pages: z.number().int().min(0),
});

export type SupplierListResponse = z.infer<typeof SupplierListResponseSchema>;

export const SupplierListParamsSchema = PaginationParamsSchema.extend({
  tier: z.number().int().min(1).max(3).optional(),
  country_code: z.string().length(2).optional(),
  min_risk_score: z.number().min(0).max(1).optional(),
});

export type SupplierListParams = z.input<typeof SupplierListParamsSchema>;

export const SupplierRiskResponseSchema = z.object({
  supplier_id: z.string(),
  neptune_node_id: z.string().nullable().optional(),
  supplier_name: z.string(),
  country_code: z.string(),
  tier: z.number().int(),
  composite_risk_score: z.union([z.number(), z.string()]),
  risk_level: z.string(),
  active_alerts_count: z.number().int().min(0).default(0),
  critical_alerts_count: z.number().int().min(0).default(0),
  total_financial_exposure_usd: z.union([z.number(), z.string()]).default('0.00'),
  total_shortage_volume: z.number().int().min(0).default(0),
  min_days_of_cover: z.union([z.number(), z.string()]).nullable().optional(),
  affected_skus: z.array(z.string()).default([]),
  affected_plants: z.array(z.string()).default([]),
  affected_programs: z.array(z.string()).default([]),
  is_single_source: z.boolean().default(false),
  evaluated_at: z.string(),
});

export type SupplierRisk = z.infer<typeof SupplierRiskResponseSchema>;

export const SubgraphNodeSchema = z.object({
  id: z.string(),
  label: z.string().optional(),
}).passthrough();

export type SubgraphNode = z.infer<typeof SubgraphNodeSchema>;

export const SubgraphEdgeSchema = z.object({
  from: z.string().optional(),
  to: z.string().optional(),
  source: z.string().optional(),
  target: z.string().optional(),
  type: z.string().optional(),
  relationship_type: z.string().optional(),
}).passthrough();

export type SubgraphEdge = z.infer<typeof SubgraphEdgeSchema>;

export const SupplierGraphResponseSchema = z.object({
  supplier_id: z.string(),
  neptune_node_id: z.string(),
  nodes: z.array(z.record(z.unknown())).default([]),
  edges: z.array(z.record(z.unknown())).default([]),
  total_nodes: z.number().int().min(0),
  total_edges: z.number().int().min(0),
  hop_depth: z.number().int().min(1).max(3).default(2),
});

export type SupplierGraphResponse = z.infer<typeof SupplierGraphResponseSchema>;

// =============================================================================
// 7. WebSocket Alert Streaming Schemas (src/api/routes/websocket_routes.py)
// =============================================================================

export const WebSocketAlertDataSchema = z.object({
  alert_id: z.string(),
  supplier_id: z.string().nullable().optional(),
  component_sku: z.string(),
  risk_level: z.string(),
  days_of_cover: z.union([z.number(), z.string()]),
  gap_days: z.union([z.number(), z.string()]).nullable().optional(),
  shortage_volume: z.number().int().min(0),
  financial_exposure: z.union([z.number(), z.string()]),
  status: z.string(),
  hitl_required: z.boolean().default(false),
  hitl_tier: z.string().nullable().optional(),
  timestamp: z.string(),
});

export type WebSocketAlertData = z.infer<typeof WebSocketAlertDataSchema>;

export const WebSocketRiskAlertEnvelopeSchema = z.object({
  type: z.literal('risk_alert'),
  data: WebSocketAlertDataSchema,
});

export type WebSocketRiskAlertEnvelope = z.infer<typeof WebSocketRiskAlertEnvelopeSchema>;

export const WebSocketSubscriptionFiltersSchema = z.object({
  risk_levels: z.union([z.string(), z.array(z.string())]).optional(),
  supplier_ids: z.union([z.string(), z.array(z.string())]).optional(),
  component_skus: z.union([z.string(), z.array(z.string())]).optional(),
});

export type WebSocketSubscriptionFilters = z.infer<typeof WebSocketSubscriptionFiltersSchema>;

export const WebSocketClientSubscribeMessageSchema = z.object({
  type: z.enum(['subscribe', 'filter']),
  risk_level: z.union([z.string(), z.array(z.string())]).optional(),
  risk_levels: z.union([z.string(), z.array(z.string())]).optional(),
  supplier_id: z.union([z.string(), z.array(z.string())]).optional(),
  supplier_ids: z.union([z.string(), z.array(z.string())]).optional(),
  sku: z.union([z.string(), z.array(z.string())]).optional(),
  component_sku: z.union([z.string(), z.array(z.string())]).optional(),
  skus: z.union([z.string(), z.array(z.string())]).optional(),
});

export type WebSocketClientSubscribeMessage = z.infer<typeof WebSocketClientSubscribeMessageSchema>;

export const WebSocketClientPingMessageSchema = z.object({
  type: z.literal('ping'),
  echo: z.unknown().optional(),
});

export type WebSocketClientPingMessage = z.infer<typeof WebSocketClientPingMessageSchema>;

export const WebSocketServerSubscribedMessageSchema = z.object({
  type: z.literal('subscribed'),
  filters: z.object({
    risk_levels: z.array(z.string()).nullable().optional(),
    supplier_ids: z.array(z.string()).nullable().optional(),
    component_skus: z.array(z.string()).nullable().optional(),
  }),
});

export type WebSocketServerSubscribedMessage = z.infer<typeof WebSocketServerSubscribedMessageSchema>;

export const WebSocketServerPongMessageSchema = z.object({
  type: z.literal('pong'),
  timestamp: z.string(),
  client_id: z.string().optional(),
  echo: z.unknown().optional(),
});

export type WebSocketServerPongMessage = z.infer<typeof WebSocketServerPongMessageSchema>;

export const WebSocketServerErrorSchema = z.object({
  type: z.literal('error'),
  message: z.string(),
});

export type WebSocketServerError = z.infer<typeof WebSocketServerErrorSchema>;

export const WebSocketServerMessageSchema = z.discriminatedUnion('type', [
  WebSocketRiskAlertEnvelopeSchema,
  WebSocketServerSubscribedMessageSchema,
  WebSocketServerPongMessageSchema,
  WebSocketServerErrorSchema,
]);

export type WebSocketServerMessage = z.infer<typeof WebSocketServerMessageSchema>;
