/**
 * Frontend API Zod Schemas Unit Tests (P12-1)
 */

import { describe, expect, it } from 'vitest';
import {
  AlertAcknowledgeRequestSchema,
  AlertAcknowledgeResponseSchema,
  ApiError,
  ApiErrorEnvelopeSchema,
  ApprovalItemSchema,
  ApprovalQueueListResponseSchema,
  ApprovalRejectRequestSchema,
  ApprovalSignRequestSchema,
  ApprovalSignResponseSchema,
  InvestigationDetailResponseSchema,
  InvestigationStartRequestSchema,
  InvestigationStartResponseSchema,
  RiskAlertListResponseSchema,
  RiskAlertSchema,
  RiskEvaluationRequestSchema,
  RiskEvaluationResponseSchema,
  SupplierGraphResponseSchema,
  SupplierListResponseSchema,
  SupplierRiskResponseSchema,
  SupplierSchema,
  WebSocketAlertDataSchema,
  WebSocketRiskAlertEnvelopeSchema,
  WebSocketServerMessageSchema,
  WebSocketSubscriptionFiltersSchema,
} from './types';

describe('Canonical Error Envelope Schema (CLAUDE.md Section 10)', () => {
  it('parses valid error envelope with trace_id and details', () => {
    const raw = {
      error: {
        code: 'TOKEN_REPLAY',
        message: 'Cryptographic token has already been consumed.',
        trace_id: 'tr-abc-123',
        details: { token_hash: 'hash-xyz' },
      },
    };
    const parsed = ApiErrorEnvelopeSchema.parse(raw);
    expect(parsed.error.code).toBe('TOKEN_REPLAY');
    expect(parsed.error.trace_id).toBe('tr-abc-123');
    expect(parsed.error.message).toContain('Cryptographic token');
  });

  it('fails validation when code or message is missing', () => {
    const raw = {
      error: {
        trace_id: 'tr-abc-123',
      },
    };
    const result = ApiErrorEnvelopeSchema.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it('constructs ApiError instance with default values', () => {
    const err = new ApiError('Test error message', 'CUSTOM_CODE', 'tr-999', 400, { foo: 'bar' });
    expect(err.name).toBe('ApiError');
    expect(err.message).toBe('Test error message');
    expect(err.code).toBe('CUSTOM_CODE');
    expect(err.traceId).toBe('tr-999');
    expect(err.statusCode).toBe(400);
    expect(err.details).toEqual({ foo: 'bar' });
  });
});

describe('Risk & Alert Schemas', () => {
  it('validates RiskEvaluationRequest payload', () => {
    const req = {
      component_sku: 'NC-2024',
      supplier_id: 'sup-123',
      current_stock: '142000',
      daily_consumption_rate: '18500',
      eta_days: '9.00',
      unit_cost_usd: '100.25',
      pipeline_mode: 'auto' as const,
    };
    const parsed = RiskEvaluationRequestSchema.parse(req);
    expect(parsed.component_sku).toBe('NC-2024');
    expect(parsed.current_stock).toBe('142000');
  });

  it('validates RiskEvaluationResponse canonical NanoCore payload', () => {
    const resp = {
      evaluation_id: 'eval-nano-1',
      alert_id: 'alert-123',
      pipeline_track: 'FAST_TRACK' as const,
      status: 'EVALUATED',
      component_sku: 'NC-2024',
      supplier_id: 'sup-nanocore',
      days_of_cover: '7.68',
      gap_days: '1.32',
      shortage_volume: 24420,
      financial_exposure_usd: '2448105.00',
      risk_level: 'CRITICAL' as const,
      requires_hitl: true,
      governing_spend_tier: 'DUAL_VP',
      evaluated_at: '2026-11-24T12:00:00Z',
    };
    const parsed = RiskEvaluationResponseSchema.parse(resp);
    expect(parsed.days_of_cover).toBe('7.68');
    expect(parsed.shortage_volume).toBe(24420);
    expect(parsed.financial_exposure_usd).toBe('2448105.00');
    expect(parsed.risk_level).toBe('CRITICAL');
  });

  it('validates RiskAlertSchema and RiskAlertListResponseSchema', () => {
    const alert = {
      id: 'alt-001',
      supplier_id: 'sup-001',
      component_sku: 'MCU-99',
      risk_level: 'HIGH',
      days_of_cover: '5.20',
      financial_exposure: '50000.00',
      shortage_volume: 500,
      status: 'OPEN',
      created_at: '2026-11-24T10:00:00Z',
    };
    const parsedAlert = RiskAlertSchema.parse(alert);
    expect(parsedAlert.id).toBe('alt-001');

    const listResp = {
      items: [alert],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    };
    const parsedList = RiskAlertListResponseSchema.parse(listResp);
    expect(parsedList.total).toBe(1);
    expect(parsedList.items).toHaveLength(1);
  });

  it('validates AlertAcknowledgeRequest & Response', () => {
    const req = { notes: 'Investigating buffer stock' };
    expect(AlertAcknowledgeRequestSchema.parse(req).notes).toBe('Investigating buffer stock');

    const resp = {
      id: 'alt-001',
      status: 'ACKNOWLEDGED' as const,
      acknowledged_by: 'usr-analyst',
      acknowledged_at: '2026-11-24T10:05:00Z',
      notes: 'Investigating buffer stock',
    };
    const parsedResp = AlertAcknowledgeResponseSchema.parse(resp);
    expect(parsedResp.status).toBe('ACKNOWLEDGED');
    expect(parsedResp.acknowledged_by).toBe('usr-analyst');
  });
});

describe('Multi-Agent Investigation Schemas', () => {
  it('validates InvestigationStartRequest and StartResponse', () => {
    const req = {
      supplier_id: 'sup-nano',
      component_sku: 'NC-2024',
      signal_type: 'news',
      raw_signal: 'Cleanroom disruption reported at plant',
    };
    const parsedReq = InvestigationStartRequestSchema.parse(req);
    expect(parsedReq.supplier_id).toBe('sup-nano');

    const startResp = {
      investigation_id: 'inv-uuid-1',
      case_id: 'CASE-2026-001',
      alert_id: 'alt-1',
      status: 'RUNNING',
      poll_url: '/api/v1/investigations/inv-uuid-1',
      started_at: '2026-11-24T10:00:00Z',
      estimated_completion_seconds: 90,
      message: 'Started successfully',
    };
    const parsedStart = InvestigationStartResponseSchema.parse(startResp);
    expect(parsedStart.case_id).toBe('CASE-2026-001');
    expect(parsedStart.estimated_completion_seconds).toBe(90);
  });

  it('validates InvestigationDetailResponse telemetry and recommendations', () => {
    const detail = {
      investigation_id: 'inv-uuid-1',
      case_id: 'CASE-2026-001',
      supplier_id: 'sup-nano',
      component_sku: 'NC-2024',
      status: 'COMPLETED',
      current_node: 'recommendation_agent',
      execution_path: ['triage_agent', 'research_agent', 'contract_agent', 'risk_agent', 'recommendation_agent'],
      risk_metrics: { days_of_cover: '7.68', financial_exposure: '2448105.00' },
      severity: 'CRITICAL',
      narrative: 'Severe disruption with 1.32 days coverage gap',
      recommendations: [
        {
          scenario_id: 'SCENARIO-1',
          action_type: 'LOGISTICS_EXPEDITE',
          estimated_cost_usd: '75000.00',
        },
      ],
      recommended_action_id: 'SCENARIO-1',
      requires_hitl: true,
      governing_spend_tier: 'PROC_DIRECTOR',
      errors: [],
      started_at: '2026-11-24T10:00:00Z',
      completed_at: '2026-11-24T10:01:15Z',
      duration_ms: 75000,
      tokens_used: 4500,
      cost_usd: '0.045000',
    };
    const parsed = InvestigationDetailResponseSchema.parse(detail);
    expect(parsed.status).toBe('COMPLETED');
    expect(parsed.requires_hitl).toBe(true);
    expect(parsed.duration_ms).toBe(75000);
    expect(parsed.tokens_used).toBe(4500);
  });
});

describe('HITL Approval Schemas', () => {
  it('validates ApprovalItem and QueueList', () => {
    const item = {
      id: 'appr-001',
      alert_id: 'alt-1',
      action_type: 'SECONDARY_SOURCE',
      amount_usd: '150000.00',
      spend_tier: 'DUAL_VP',
      token_hash: 'sha256-hash-val',
      approved_by: ['usr-dir'],
      approved_at: ['2026-11-24T11:00:00Z'],
      status: 'PARTIALLY_APPROVED',
      expires_at: '2026-11-24T11:30:00Z',
      created_at: '2026-11-24T11:00:00Z',
    };
    const parsedItem = ApprovalItemSchema.parse(item);
    expect(parsedItem.spend_tier).toBe('DUAL_VP');
    expect(parsedItem.status).toBe('PARTIALLY_APPROVED');

    const queue = {
      items: [item],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    };
    const parsedQueue = ApprovalQueueListResponseSchema.parse(queue);
    expect(parsedQueue.items).toHaveLength(1);
  });

  it('validates ApprovalSignRequest & ApprovalSignResponse', () => {
    const req = {
      token: 'kms-ecdsa-p256-base64-token-string-example',
      notes: 'Sign-off approved per risk report',
    };
    expect(ApprovalSignRequestSchema.parse(req).token).toContain('kms-ecdsa');

    const resp = {
      id: 'appr-001',
      status: 'APPROVED',
      action_type: 'SECONDARY_SOURCE',
      amount_usd: '25000.00',
      spend_tier: 'CATEGORY_MGR',
      approved_by: ['usr-cat-mgr'],
      approved_at: ['2026-11-24T11:05:00Z'],
      message: 'Signature verified successfully',
    };
    const parsedResp = ApprovalSignResponseSchema.parse(resp);
    expect(parsedResp.status).toBe('APPROVED');
    expect(parsedResp.spend_tier).toBe('CATEGORY_MGR');
  });

  it('validates ApprovalRejectRequest', () => {
    const req = { justification: 'Unfavorable contract liability terms' };
    expect(ApprovalRejectRequestSchema.parse(req).justification).toContain('Unfavorable');
    expect(ApprovalRejectRequestSchema.safeParse({ justification: '' }).success).toBe(false);
  });
});

describe('Supplier Intelligence Schemas', () => {
  it('validates Supplier & SupplierListResponse', () => {
    const supp = {
      id: 'sup-001',
      name: 'NanoCore Semiconductor GmbH',
      country_code: 'DE',
      tier: 1,
      risk_score: '0.875',
      neptune_node_id: 'SUP-NC-882',
      created_at: '2026-11-20T00:00:00Z',
      updated_at: '2026-11-24T10:00:00Z',
    };
    expect(SupplierSchema.parse(supp).tier).toBe(1);

    const list = {
      items: [supp],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    };
    expect(SupplierListResponseSchema.parse(list).total).toBe(1);
  });

  it('validates SupplierRiskResponse', () => {
    const risk = {
      supplier_id: 'sup-001',
      neptune_node_id: 'SUP-NC-882',
      supplier_name: 'NanoCore Semiconductor GmbH',
      country_code: 'DE',
      tier: 1,
      composite_risk_score: '0.920',
      risk_level: 'CRITICAL',
      active_alerts_count: 2,
      critical_alerts_count: 1,
      total_financial_exposure_usd: '2448105.00',
      total_shortage_volume: 24420,
      min_days_of_cover: '7.68',
      affected_skus: ['NC-2024'],
      affected_plants: ['PLT-MUC-01'],
      affected_programs: ['PGM-APEX-SUV'],
      is_single_source: true,
      evaluated_at: '2026-11-24T12:00:00Z',
    };
    const parsed = SupplierRiskResponseSchema.parse(risk);
    expect(parsed.composite_risk_score).toBe('0.920');
    expect(parsed.is_single_source).toBe(true);
    expect(parsed.affected_skus).toContain('NC-2024');
  });

  it('validates SupplierGraphResponse 2-hop topology', () => {
    const graph = {
      supplier_id: 'sup-001',
      neptune_node_id: 'SUP-NC-882',
      nodes: [
        { id: 'SUP-NC-882', label: 'Supplier', name: 'NanoCore' },
        { id: 'NC-2024', label: 'Component', sku: 'NC-2024' },
      ],
      edges: [
        { from: 'SUP-NC-882', to: 'NC-2024', type: 'SUPPLIES_PART' },
      ],
      total_nodes: 2,
      total_edges: 1,
      hop_depth: 2,
    };
    const parsed = SupplierGraphResponseSchema.parse(graph);
    expect(parsed.total_nodes).toBe(2);
    expect(parsed.nodes).toHaveLength(2);
  });
});

describe('WebSocket Message Schemas', () => {
  it('validates WebSocketAlertData & RiskAlertEnvelope', () => {
    const alertData = {
      alert_id: 'alt-live-1',
      supplier_id: 'sup-001',
      component_sku: 'NC-2024',
      risk_level: 'CRITICAL',
      days_of_cover: '7.68',
      gap_days: '1.32',
      shortage_volume: 24420,
      financial_exposure: '2448105.00',
      status: 'OPEN',
      hitl_required: true,
      hitl_tier: 'DUAL_VP',
      timestamp: '2026-11-24T12:00:00Z',
    };
    const parsedAlert = WebSocketAlertDataSchema.parse(alertData);
    expect(parsedAlert.days_of_cover).toBe('7.68');

    const envelope = {
      type: 'risk_alert' as const,
      data: alertData,
    };
    const parsedEnv = WebSocketRiskAlertEnvelopeSchema.parse(envelope);
    expect(parsedEnv.type).toBe('risk_alert');
  });

  it('validates WebSocketServerMessage union discriminated by type', () => {
    const subscribed = {
      type: 'subscribed' as const,
      filters: {
        risk_levels: ['CRITICAL'],
        supplier_ids: null,
        component_skus: ['NC-2024'],
      },
    };
    const parsedSub = WebSocketServerMessageSchema.parse(subscribed);
    expect(parsedSub.type).toBe('subscribed');

    const pong = {
      type: 'pong' as const,
      timestamp: '2026-11-24T12:00:00Z',
      client_id: 'cli-001',
      echo: 'ping-1',
    };
    const parsedPong = WebSocketServerMessageSchema.parse(pong);
    expect(parsedPong.type).toBe('pong');

    const errorMsg = {
      type: 'error' as const,
      message: 'Unknown command',
    };
    const parsedErr = WebSocketServerMessageSchema.parse(errorMsg);
    expect(parsedErr.type).toBe('error');
  });

  it('validates WebSocketSubscriptionFiltersSchema', () => {
    const filters = {
      risk_levels: ['CRITICAL', 'HIGH'],
      supplier_ids: 'sup-1',
    };
    const parsed = WebSocketSubscriptionFiltersSchema.parse(filters);
    expect(parsed.risk_levels).toEqual(['CRITICAL', 'HIGH']);
  });
});
