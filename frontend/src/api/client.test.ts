/**
 * Frontend Axios Client & Interceptor Unit Tests (P12-1)
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  apiClient,
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  createApiClient,
  generateTraceId,
  getAuthToken,
  setAuthToken,
} from './client';
import { ApiError } from './types';

describe('Token Storage & Trace ID Utilities', () => {
  beforeEach(() => {
    setAuthToken(null);
  });

  afterEach(() => {
    setAuthToken(null);
  });

  it('manages auth token lifecycle in memory and storage', () => {
    expect(getAuthToken()).toBeNull();
    setAuthToken('jwt-sample-token-123');
    expect(getAuthToken()).toBe('jwt-sample-token-123');
    setAuthToken(null);
    expect(getAuthToken()).toBeNull();
  });

  it('generates unique trace IDs with req- prefix', () => {
    const id1 = generateTraceId();
    const id2 = generateTraceId();
    expect(id1).toMatch(/^req-/);
    expect(id2).toMatch(/^req-/);
    expect(id1).not.toBe(id2);
  });
});

describe('Axios Client Interceptors & Canonical Error Normalization', () => {
  beforeEach(() => {
    setAuthToken(null);
  });

  afterEach(() => {
    setAuthToken(null);
  });

  it('injects Authorization header and X-Request-ID in request interceptor', async () => {
    const client = createApiClient('http://test-server');
    setAuthToken('test-bearer-token');

    // Test request interceptor directly
    // @ts-expect-error accessing internal interceptor handlers for test
    const requestInterceptor = client.interceptors.request.handlers[0];

    const config = {
      headers: {} as Record<string, string>,
    };

    const updated = await requestInterceptor.fulfilled(config as never);
    expect(updated.headers.Authorization).toBe('Bearer test-bearer-token');
    expect(updated.headers['X-Request-ID']).toMatch(/^req-/);
  });

  it('does not overwrite existing Authorization header', async () => {
    const client = createApiClient('http://test-server');
    setAuthToken('fallback-token');

    // @ts-expect-error accessing internal interceptor handlers for test
    const requestInterceptor = client.interceptors.request.handlers[0];

    const config = {
      headers: { Authorization: 'Bearer explicit-token' } as Record<string, string>,
    };

    const updated = await requestInterceptor.fulfilled(config as never);
    expect(updated.headers.Authorization).toBe('Bearer explicit-token');
  });

  it('transforms canonical error envelope { error: { code, message, trace_id } } into ApiError', async () => {
    const client = createApiClient('http://test-server');
    // @ts-expect-error accessing internal interceptor handlers for test
    const responseInterceptor = client.interceptors.response.handlers[0];

    const mockAxiosError = {
      response: {
        status: 409,
        headers: {},
        data: {
          error: {
            code: 'NO_OP_MUTATION_REJECTED',
            message: 'Alert is already in ACKNOWLEDGED status.',
            trace_id: 'req-trace-409',
            details: { current_status: 'ACKNOWLEDGED' },
          },
        },
      },
    };

    const rejectHandler = responseInterceptor.rejected!;

    await expect(rejectHandler(mockAxiosError)).rejects.toThrow(ApiError);

    try {
      await rejectHandler(mockAxiosError);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe('NO_OP_MUTATION_REJECTED');
      expect(apiErr.message).toBe('Alert is already in ACKNOWLEDGED status.');
      expect(apiErr.traceId).toBe('req-trace-409');
      expect(apiErr.statusCode).toBe(409);
      expect(apiErr.details).toEqual({ current_status: 'ACKNOWLEDGED' });
    }
  });

  it('handles unstructured 500 error responses gracefully', async () => {
    const client = createApiClient('http://test-server');
    // @ts-expect-error accessing internal interceptor handlers for test
    const responseInterceptor = client.interceptors.response.handlers[0];

    const mockAxiosError = {
      response: {
        status: 500,
        headers: { 'x-trace-id': 'tr-header-500' },
        data: { detail: 'Database connection failed' },
      },
    };

    const rejectHandler = responseInterceptor.rejected!;

    try {
      await rejectHandler(mockAxiosError);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe('HTTP_500');
      expect(apiErr.message).toBe('Database connection failed');
      expect(apiErr.traceId).toBe('tr-header-500');
      expect(apiErr.statusCode).toBe(500);
    }
  });

  it('handles network timeouts (ECONNABORTED)', async () => {
    const client = createApiClient('http://test-server');
    // @ts-expect-error accessing internal interceptor handlers for test
    const responseInterceptor = client.interceptors.response.handlers[0];

    const mockAxiosError = {
      code: 'ECONNABORTED',
      message: 'timeout of 30000ms exceeded',
    };

    const rejectHandler = responseInterceptor.rejected!;

    try {
      await rejectHandler(mockAxiosError);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe('REQUEST_TIMEOUT');
      expect(apiErr.statusCode).toBe(408);
    }
  });

  it('handles network connectivity failures (request without response)', async () => {
    const client = createApiClient('http://test-server');
    // @ts-expect-error accessing internal interceptor handlers for test
    const responseInterceptor = client.interceptors.response.handlers[0];

    const mockAxiosError = {
      request: {},
      message: 'Network Error',
    };

    const rejectHandler = responseInterceptor.rejected!;

    try {
      await rejectHandler(mockAxiosError);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe('NETWORK_ERROR');
      expect(apiErr.statusCode).toBe(0);
      expect(apiErr.message).toContain('Unable to communicate');
    }
  });

  it('passes successful response data untouched', async () => {
    const client = createApiClient('http://test-server');
    // @ts-expect-error accessing internal interceptor handlers for test
    const responseInterceptor = client.interceptors.response.handlers[0];

    const mockResponse = {
      status: 200,
      data: { status: 'ok', value: 42 },
    };

    const res = await responseInterceptor.fulfilled(mockResponse as never);
    expect(res.data).toEqual({ status: 'ok', value: 42 });
  });
});

describe('Typed HTTP Wrappers Export Checks', () => {
  it('exports apiClient and helper methods', () => {
    expect(apiClient).toBeDefined();
    expect(typeof apiGet).toBe('function');
    expect(typeof apiPost).toBe('function');
    expect(typeof apiPut).toBe('function');
    expect(typeof apiDelete).toBe('function');
  });
});
