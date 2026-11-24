/**
 * Frontend Axios API Client (P12-1)
 *
 * Configures the base HTTP client with:
 * - Environment-driven baseURL resolution (Vite dev proxy or VITE_API_URL)
 * - Request interceptor: Keycloak/Okta JWT Bearer token injection and X-Request-ID tracing header
 * - Response interceptor: Canonical error envelope normalization into strongly-typed ApiError
 * - Helper methods with full TypeScript generics
 */

import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios';
import { ApiError, ApiErrorEnvelopeSchema } from './types';

// =============================================================================
// Token & Session Storage
// =============================================================================

let activeAuthToken: string | null = null;

export const setAuthToken = (token: string | null): void => {
  activeAuthToken = token;
  if (typeof window !== 'undefined' && window.localStorage) {
    if (token) {
      localStorage.setItem('apexmotion_auth_token', token);
    } else {
      localStorage.removeItem('apexmotion_auth_token');
    }
  }
};

export const getAuthToken = (): string | null => {
  if (activeAuthToken) {
    return activeAuthToken;
  }
  if (typeof window !== 'undefined' && window.localStorage) {
    return localStorage.getItem('apexmotion_auth_token');
  }
  return null;
};

// =============================================================================
// Distributed Tracing Utilities
// =============================================================================

export const generateTraceId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `req-${crypto.randomUUID()}`;
  }
  return `req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
};

// =============================================================================
// Axios Client Initialization
// =============================================================================

const getBaseUrl = (): string => {
  // Check Vite environment variable, fallback to relative path (handled by Vite proxy)
  if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  return '';
};

export const createApiClient = (baseURL = getBaseUrl()): AxiosInstance => {
  const instance = axios.create({
    baseURL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  });

  // Request Interceptor: Auth & Tracing
  instance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = getAuthToken();
      if (token && !config.headers.Authorization) {
        config.headers.Authorization = `Bearer ${token}`;
      }

      if (!config.headers['X-Request-ID']) {
        config.headers['X-Request-ID'] = generateTraceId();
      }

      return config;
    },
    (error) => Promise.reject(error)
  );

  // Response Interceptor: Canonical Error Envelope Transformation
  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      // 1. Check for API response with canonical { error: { code, message, trace_id, details } }
      if (error.response?.data) {
        const parsedEnvelope = ApiErrorEnvelopeSchema.safeParse(error.response.data);
        if (parsedEnvelope.success) {
          const { code, message, trace_id, details } = parsedEnvelope.data.error;
          return Promise.reject(
            new ApiError(message, code, trace_id, error.response.status, details)
          );
        }

        // If data is a plain string or unstructured JSON
        const rawData = error.response.data as Record<string, unknown>;
        const rawDetail = typeof rawData === 'object' && rawData !== null ? rawData.detail : undefined;
        const fallbackMessage = typeof rawDetail === 'string'
          ? rawDetail
          : error.message || 'Server returned an unformatted error response';

        return Promise.reject(
          new ApiError(
            fallbackMessage,
            `HTTP_${error.response.status}`,
            (error.response.headers['x-trace-id'] as string) || 'unknown',
            error.response.status,
            rawData
          )
        );
      }

      // 2. Network timeout or unreachable service
      if (error.code === 'ECONNABORTED') {
        return Promise.reject(
          new ApiError('Request timed out. Please retry.', 'REQUEST_TIMEOUT', 'unknown', 408)
        );
      }

      if (error.request) {
        return Promise.reject(
          new ApiError(
            'Unable to communicate with the ApexMotion server. Please check your network connection.',
            'NETWORK_ERROR',
            'unknown',
            0
          )
        );
      }

      // 3. Fallback generic error
      return Promise.reject(
        new ApiError(error.message || 'An unexpected client error occurred', 'CLIENT_ERROR', 'unknown', 500)
      );
    }
  );

  return instance;
};

export const apiClient = createApiClient();

// =============================================================================
// Typed HTTP Method Wrappers
// =============================================================================

export const apiGet = async <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
  const response = await apiClient.get<T>(url, config);
  return response.data;
};

export const apiPost = async <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> => {
  const response = await apiClient.post<T>(url, data, config);
  return response.data;
};

export const apiPut = async <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> => {
  const response = await apiClient.put<T>(url, data, config);
  return response.data;
};

export const apiDelete = async <T>(url: string, config?: AxiosRequestConfig): Promise<T> => {
  const response = await apiClient.delete<T>(url, config);
  return response.data;
};
