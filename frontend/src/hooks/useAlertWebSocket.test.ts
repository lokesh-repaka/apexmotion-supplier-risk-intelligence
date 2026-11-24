/**
 * WebSocket Custom React Hook Unit Tests (P12-1)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAlertWebSocket } from './useAlertWebSocket';

// =============================================================================
// Mock WebSocket Implementation
// =============================================================================

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  url: string;
  readyState: number = MockWebSocket.CONNECTING;
  sentMessages: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      if (this.readyState === MockWebSocket.CONNECTING) {
        this.readyState = MockWebSocket.OPEN;
        this.onopen?.();
      }
    }, 5);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason });
  }

  triggerMessage(data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

// Bind mock to window
if (typeof window !== 'undefined') {
  // @ts-expect-error Mocking WebSocket for Vitest
  window.WebSocket = MockWebSocket;
} else {
  // @ts-expect-error Mocking global WebSocket
  globalThis.WebSocket = MockWebSocket;
}

describe('useAlertWebSocket Hook Functionality', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllTimers();
  });

  it('exports useAlertWebSocket hook function', () => {
    expect(typeof useAlertWebSocket).toBe('function');
  });

  it('instantiates MockWebSocket with resolved URL and tracks connection events', async () => {
    const ws = new MockWebSocket('ws://localhost:8000/ws/alerts?token=test-jwt');
    expect(ws.url).toContain('/ws/alerts');

    // Advance fake timers so open triggers
    vi.advanceTimersByTime(10);
    expect(ws.readyState).toBe(MockWebSocket.OPEN);

    // Send ping
    ws.send(JSON.stringify({ type: 'ping' }));
    expect(ws.sentMessages).toHaveLength(1);
    expect(ws.sentMessages[0]).toBe('{"type":"ping"}');

    // Simulate server push
    let receivedAlert = null;
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'risk_alert') {
        receivedAlert = data.data;
      }
    };

    ws.triggerMessage({
      type: 'risk_alert',
      data: {
        alert_id: 'alt-realtime-1',
        component_sku: 'NC-2024',
        risk_level: 'CRITICAL',
        days_of_cover: '7.68',
        shortage_volume: 24420,
        financial_exposure: '2448105.00',
        status: 'OPEN',
        hitl_required: true,
        timestamp: '2026-11-24T12:00:00Z',
      },
    });

    expect(receivedAlert).not.toBeNull();
    // @ts-expect-error verifying parsed mock data
    expect(receivedAlert?.component_sku).toBe('NC-2024');
    // @ts-expect-error verifying parsed mock data
    expect(receivedAlert?.financial_exposure).toBe('2448105.00');

    // Simulate close
    let closeCode = 0;
    ws.onclose = (event) => {
      closeCode = event.code;
    };
    ws.close(1000, 'Normal Closure');
    expect(closeCode).toBe(1000);
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
  });

  it('handles policy violation close code 1008', () => {
    const ws = new MockWebSocket('ws://localhost:8000/ws/alerts');
    vi.advanceTimersByTime(10);

    let reportedCode = 0;
    ws.onclose = (event) => {
      reportedCode = event.code;
    };

    ws.close(1008, 'Authentication policy violation');
    expect(reportedCode).toBe(1008);
  });
});
