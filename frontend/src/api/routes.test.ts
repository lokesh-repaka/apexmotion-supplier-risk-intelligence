/**
 * Frontend Route API Modules Unit Tests (P12-1)
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from './client';
import { approvalApi } from './routes/approvals';
import { investigationApi } from './routes/investigations';
import { riskApi } from './routes/risk';
import { supplierApi } from './routes/suppliers';

describe('Risk API Routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('evaluates risk via POST /api/v1/risk/evaluate', async () => {
    const mockResponse = {
      data: {
        evaluation_id: 'eval-1',
        pipeline_track: 'FAST_TRACK',
        status: 'EVALUATED',
        component_sku: 'NC-2024',
        days_of_cover: '7.68',
        gap_days: '1.32',
        shortage_volume: 24420,
        financial_exposure_usd: '2448105.00',
        risk_level: 'CRITICAL',
        requires_hitl: true,
        evaluated_at: '2026-11-24T12:00:00Z',
      },
    };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const result = await riskApi.evaluateRisk({
      component_sku: 'NC-2024',
      current_stock: '142000',
      daily_consumption_rate: '18500',
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/risk/evaluate',
      expect.objectContaining({ component_sku: 'NC-2024' }),
      undefined
    );
    expect(result.days_of_cover).toBe('7.68');
    expect(result.financial_exposure_usd).toBe('2448105.00');
  });

  it('fetches alerts via GET /api/v1/alerts', async () => {
    const mockResponse = {
      data: {
        items: [
          {
            id: 'alt-1',
            component_sku: 'NC-2024',
            risk_level: 'CRITICAL',
            status: 'OPEN',
            created_at: '2026-11-24T12:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const result = await riskApi.getAlerts({ risk_level: 'CRITICAL' });
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/alerts', {
      params: { risk_level: 'CRITICAL' },
    });
    expect(result.items).toHaveLength(1);
    expect(result.items[0].component_sku).toBe('NC-2024');
  });

  it('fetches a single alert by ID via GET /api/v1/alerts/{id}', async () => {
    const mockResponse = {
      data: {
        id: 'alt-1',
        component_sku: 'NC-2024',
        risk_level: 'CRITICAL',
        status: 'OPEN',
        created_at: '2026-11-24T12:00:00Z',
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const alert = await riskApi.getAlert('alt-1');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/alerts/alt-1', undefined);
    expect(alert.id).toBe('alt-1');
  });

  it('acknowledges an alert via POST /api/v1/alerts/{id}/acknowledge', async () => {
    const mockResponse = {
      data: {
        id: 'alt-1',
        status: 'ACKNOWLEDGED',
        acknowledged_by: 'usr-analyst',
        acknowledged_at: '2026-11-24T12:05:00Z',
        notes: 'Triaged by analyst',
      },
    };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const res = await riskApi.acknowledgeAlert('alt-1', { notes: 'Triaged by analyst' });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/alerts/alt-1/acknowledge',
      { notes: 'Triaged by analyst' },
      undefined
    );
    expect(res.status).toBe('ACKNOWLEDGED');
  });
});

describe('Investigation API Routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('starts investigation via POST /api/v1/investigations/start', async () => {
    const mockResponse = {
      data: {
        investigation_id: 'inv-123',
        case_id: 'CASE-2026-001',
        alert_id: 'alt-1',
        status: 'RUNNING',
        poll_url: '/api/v1/investigations/inv-123',
        started_at: '2026-11-24T12:00:00Z',
        estimated_completion_seconds: 90,
      },
    };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const res = await investigationApi.startInvestigation({
      supplier_id: 'sup-1',
      component_sku: 'NC-2024',
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/investigations/start',
      expect.objectContaining({ supplier_id: 'sup-1' }),
      undefined
    );
    expect(res.case_id).toBe('CASE-2026-001');
  });

  it('fetches investigation status via GET /api/v1/investigations/{id}', async () => {
    const mockResponse = {
      data: {
        investigation_id: 'inv-123',
        case_id: 'CASE-2026-001',
        supplier_id: 'sup-1',
        status: 'COMPLETED',
        started_at: '2026-11-24T12:00:00Z',
        execution_path: ['triage_agent', 'risk_agent'],
        requires_hitl: false,
        errors: [],
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await investigationApi.getInvestigation('inv-123');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/investigations/inv-123', undefined);
    expect(res.status).toBe('COMPLETED');
  });

  it('fetches case dossier via GET /api/v1/cases/{case_id}', async () => {
    const mockResponse = {
      data: {
        investigation_id: 'inv-123',
        case_id: 'CASE-2026-001',
        supplier_id: 'sup-1',
        status: 'AWAITING_APPROVAL',
        started_at: '2026-11-24T12:00:00Z',
        requires_hitl: true,
        governing_spend_tier: 'PROC_DIRECTOR',
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await investigationApi.getCase('CASE-2026-001');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/cases/CASE-2026-001', undefined);
    expect(res.governing_spend_tier).toBe('PROC_DIRECTOR');
  });
});

describe('HITL Approval API Routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches approvals queue via GET /api/v1/approvals', async () => {
    const mockResponse = {
      data: {
        items: [
          {
            id: 'appr-1',
            action_type: 'SECONDARY_SOURCE',
            amount_usd: '50000.00',
            spend_tier: 'PROC_DIRECTOR',
            token_hash: 'hash-1',
            status: 'PENDING',
            expires_at: '2026-11-24T13:00:00Z',
            created_at: '2026-11-24T12:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await approvalApi.getApprovals({ status: 'PENDING' });
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/approvals', {
      params: { status: 'PENDING' },
    });
    expect(res.items[0].spend_tier).toBe('PROC_DIRECTOR');
  });

  it('signs approval via POST /api/v1/approvals/{id}/sign', async () => {
    const mockResponse = {
      data: {
        id: 'appr-1',
        status: 'APPROVED',
        action_type: 'SECONDARY_SOURCE',
        amount_usd: '50000.00',
        spend_tier: 'PROC_DIRECTOR',
        approved_by: ['usr-dir'],
        approved_at: ['2026-11-24T12:10:00Z'],
        message: 'Signed',
      },
    };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const res = await approvalApi.signApproval('appr-1', {
      token: 'valid-kms-ecdsa-p256-token',
      notes: 'Approved',
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/approvals/appr-1/sign',
      { token: 'valid-kms-ecdsa-p256-token', notes: 'Approved' },
      undefined
    );
    expect(res.status).toBe('APPROVED');
  });

  it('rejects approval via POST /api/v1/approvals/{id}/reject', async () => {
    const mockResponse = {
      data: {
        id: 'appr-1',
        action_type: 'SECONDARY_SOURCE',
        amount_usd: '50000.00',
        spend_tier: 'PROC_DIRECTOR',
        token_hash: 'hash-1',
        status: 'REJECTED',
        expires_at: '2026-11-24T13:00:00Z',
        created_at: '2026-11-24T12:00:00Z',
      },
    };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const res = await approvalApi.rejectApproval('appr-1', {
      justification: 'Cost exceeds budget allocation',
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/approvals/appr-1/reject',
      { justification: 'Cost exceeds budget allocation' },
      undefined
    );
    expect(res.status).toBe('REJECTED');
  });
});

describe('Supplier Intelligence API Routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches supplier list via GET /api/v1/suppliers', async () => {
    const mockResponse = {
      data: {
        items: [
          {
            id: 'sup-1',
            name: 'NanoCore',
            country_code: 'DE',
            tier: 1,
            created_at: '2026-11-20T00:00:00Z',
            updated_at: '2026-11-24T00:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await supplierApi.getSuppliers({ tier: 1 });
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/suppliers', {
      params: { tier: 1 },
    });
    expect(res.items[0].name).toBe('NanoCore');
  });

  it('fetches supplier risk profile via GET /api/v1/suppliers/{id}/risk', async () => {
    const mockResponse = {
      data: {
        supplier_id: 'sup-1',
        supplier_name: 'NanoCore',
        country_code: 'DE',
        tier: 1,
        composite_risk_score: '0.920',
        risk_level: 'CRITICAL',
        total_financial_exposure_usd: '2448105.00',
        total_shortage_volume: 24420,
        is_single_source: true,
        evaluated_at: '2026-11-24T12:00:00Z',
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await supplierApi.getSupplierRisk('sup-1');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/suppliers/sup-1/risk', undefined);
    expect(res.composite_risk_score).toBe('0.920');
  });

  it('fetches 2-hop ego-subgraph via GET /api/v1/suppliers/{id}/graph', async () => {
    const mockResponse = {
      data: {
        supplier_id: 'sup-1',
        neptune_node_id: 'SUP-NC-882',
        nodes: [{ id: 'SUP-NC-882' }],
        edges: [],
        total_nodes: 1,
        total_edges: 0,
        hop_depth: 2,
      },
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockResponse);

    const res = await supplierApi.getSupplierGraph('sup-1', 2);
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/suppliers/sup-1/graph', {
      params: { max_depth: 2 },
    });
    expect(res.neptune_node_id).toBe('SUP-NC-882');
  });
});
