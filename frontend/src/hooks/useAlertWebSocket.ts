/**
 * React WebSocket Hook for Real-Time Risk Alerts (P12-1)
 *
 * Implements:
 * - Live bidirectional connection to `/ws/alerts` or `/api/v1/ws/alerts`
 * - Automatic exponential backoff reconnection with jitter
 * - Periodic ping/pong heartbeats to keep sockets alive and detect stale connections
 * - Dynamic subscription filter updates (`risk_level`, `supplier_id`, `component_sku`)
 * - Zod schema validation of incoming alert payloads with exact Decimal preservation
 * - Clean teardown and memory-leak prevention on component unmount
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../api/client';
import {
  type WebSocketAlertData,
  WebSocketRiskAlertEnvelopeSchema,
  type WebSocketSubscriptionFilters,
} from '../api/types';

export interface UseAlertWebSocketOptions {
  /** Explicit WebSocket URL (e.g. ws://localhost:8000/ws/alerts). Defaults to window.location host. */
  url?: string;
  /** Optional JWT authentication token. If omitted, checks active auth token. */
  token?: string | null;
  /** Unique client identifier string. */
  clientId?: string;
  /** Initial subscription filters to apply upon connection. */
  initialFilters?: WebSocketSubscriptionFilters;
  /** Callback triggered whenever a validated risk alert is pushed. */
  onAlert?: (alert: WebSocketAlertData) => void;
  /** Whether to automatically reconnect upon disconnect or error. Defaults to true. */
  autoReconnect?: boolean;
  /** Initial reconnection retry delay in milliseconds. Defaults to 2000. */
  reconnectIntervalMs?: number;
  /** Maximum reconnection retry delay cap in milliseconds. Defaults to 30000. */
  maxReconnectIntervalMs?: number;
  /** Heartbeat ping interval in milliseconds. Defaults to 30000 (30 seconds). */
  heartbeatIntervalMs?: number;
  /** Maximum number of historical alerts to retain in memory. Defaults to 50. */
  maxAlertHistory?: number;
}

export interface UseAlertWebSocketReturn {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  alerts: WebSocketAlertData[];
  latestAlert: WebSocketAlertData | null;
  activeFilters: WebSocketSubscriptionFilters | null;
  updateFilters: (filters: WebSocketSubscriptionFilters) => void;
  sendPing: (echo?: unknown) => void;
  reconnect: () => void;
  clearAlerts: () => void;
}

const resolveDefaultWsUrl = (token?: string | null, clientId?: string): string => {
  if (typeof window === 'undefined') {
    return 'ws://localhost:8000/ws/alerts';
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const baseUrl = `${protocol}//${host}/ws/alerts`;

  const params = new URLSearchParams();
  const effectiveToken = token !== undefined ? token : getAuthToken();
  if (effectiveToken) {
    params.set('token', effectiveToken);
  }
  if (clientId) {
    params.set('client_id', clientId);
  }

  const query = params.toString();
  return query ? `${baseUrl}?${query}` : baseUrl;
};

export const useAlertWebSocket = (
  options: UseAlertWebSocketOptions = {}
): UseAlertWebSocketReturn => {
  const {
    url,
    token,
    clientId,
    initialFilters,
    onAlert,
    autoReconnect = true,
    reconnectIntervalMs = 2000,
    maxReconnectIntervalMs = 30000,
    heartbeatIntervalMs = 30000,
    maxAlertHistory = 50,
  } = options;

  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<WebSocketAlertData[]>([]);
  const [latestAlert, setLatestAlert] = useState<WebSocketAlertData | null>(null);
  const [activeFilters, setActiveFilters] = useState<WebSocketSubscriptionFilters | null>(
    initialFilters ?? null
  );

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isExplicitlyClosedRef = useRef<boolean>(false);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  const cleanupTimers = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  const sendPing = useCallback((echo?: unknown) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      try {
        socketRef.current.send(JSON.stringify({ type: 'ping', echo }));
      } catch (err) {
        console.warn('[useAlertWebSocket] Failed to send ping:', err);
      }
    }
  }, []);

  const updateFilters = useCallback((filters: WebSocketSubscriptionFilters) => {
    setActiveFilters(filters);
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      try {
        socketRef.current.send(
          JSON.stringify({
            type: 'subscribe',
            risk_level: filters.risk_levels,
            supplier_id: filters.supplier_ids,
            component_sku: filters.component_skus,
          })
        );
      } catch (err) {
        console.warn('[useAlertWebSocket] Failed to update filters:', err);
      }
    }
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
    setLatestAlert(null);
  }, []);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    // Close any previous open instance
    if (socketRef.current) {
      socketRef.current.close(1000, 'Reconnecting');
      socketRef.current = null;
    }

    cleanupTimers();
    setIsConnecting(true);
    setError(null);

    const targetUrl = url || resolveDefaultWsUrl(token, clientId);

    try {
      const ws = new WebSocket(targetUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        reconnectAttemptsRef.current = 0;

        // Apply initial or active subscription filters if defined
        if (activeFilters) {
          ws.send(
            JSON.stringify({
              type: 'subscribe',
              risk_level: activeFilters.risk_levels,
              supplier_id: activeFilters.supplier_ids,
              component_sku: activeFilters.component_skus,
            })
          );
        }

        // Start heartbeat ping cycle
        if (heartbeatIntervalMs > 0) {
          heartbeatIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }));
            }
          }, heartbeatIntervalMs);
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const raw = JSON.parse(event.data);

          // 1. Process risk alert event
          if (raw?.type === 'risk_alert') {
            const parsed = WebSocketRiskAlertEnvelopeSchema.safeParse(raw);
            if (parsed.success) {
              const alert = parsed.data.data;
              setLatestAlert(alert);
              setAlerts((prev) => [alert, ...prev].slice(0, maxAlertHistory));
              if (onAlertRef.current) {
                onAlertRef.current(alert);
              }
            } else {
              console.warn(
                '[useAlertWebSocket] Invalid alert schema received:',
                parsed.error
              );
            }
            return;
          }

          // 2. Process subscription acknowledgment
          if (raw?.type === 'subscribed') {
            if (raw.filters) {
              setActiveFilters({
                risk_levels: raw.filters.risk_levels ?? undefined,
                supplier_ids: raw.filters.supplier_ids ?? undefined,
                component_skus: raw.filters.component_skus ?? undefined,
              });
            }
            return;
          }

          // 3. Process pong heartbeat response
          if (raw?.type === 'pong') {
            // Heartbeat acknowledged
            return;
          }

          // 4. Process error envelope
          if (raw?.type === 'error') {
            setError(raw.message || 'Server WebSocket error');
            return;
          }
        } catch (err) {
          console.warn('[useAlertWebSocket] Failed to parse message:', err);
        }
      };

      ws.onerror = () => {
        setError('WebSocket encountered a network or protocol error');
      };

      ws.onclose = (event: CloseEvent) => {
        setIsConnected(false);
        setIsConnecting(false);
        cleanupTimers();

        if (event.code === 1008) {
          setError('Authentication policy violation. Token may be invalid or expired.');
          return; // Do not reconnect on policy violations
        }

        if (!isExplicitlyClosedRef.current && autoReconnect) {
          reconnectAttemptsRef.current += 1;
          const exponent = Math.min(reconnectAttemptsRef.current, 5);
          const baseDelay = reconnectIntervalMs * Math.pow(1.5, exponent);
          const jitter = Math.random() * 500;
          const delay = Math.min(baseDelay + jitter, maxReconnectIntervalMs);

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        }
      };
    } catch (err) {
      setIsConnecting(false);
      setError(err instanceof Error ? err.message : 'Failed to instantiate WebSocket');
    }
  }, [
    url,
    token,
    clientId,
    activeFilters,
    autoReconnect,
    reconnectIntervalMs,
    maxReconnectIntervalMs,
    heartbeatIntervalMs,
    maxAlertHistory,
    cleanupTimers,
  ]);

  const reconnect = useCallback(() => {
    isExplicitlyClosedRef.current = false;
    reconnectAttemptsRef.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    isExplicitlyClosedRef.current = false;
    connect();

    return () => {
      isExplicitlyClosedRef.current = true;
      cleanupTimers();
      if (socketRef.current) {
        socketRef.current.close(1000, 'Component unmounted');
        socketRef.current = null;
      }
    };
  }, [connect, cleanupTimers]);

  return {
    isConnected,
    isConnecting,
    error,
    alerts,
    latestAlert,
    activeFilters,
    updateFilters,
    sendPing,
    reconnect,
    clearAlerts,
  };
};
