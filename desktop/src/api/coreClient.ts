import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import {
  apiRequest,
  DEFAULT_CHAT_TIMEOUT_MS,
  DEFAULT_GENERATION_TIMEOUT_MS
} from '../lib/apiClient';
import type { ChatRole } from '../store/chatStore';

export interface ChatRequest {
  message: string;
  role: ChatRole;
  session_id: string;
}

export interface ChatResponse {
  reply: string;
  session_id?: string;
  agents_used?: string[];
  confidence?: number | null;
  conflict_rate?: number | null;
}

export interface ChatResponseMeta {
  agents?: string[];
  confidence?: number;
}

export interface TKRequest {
  work_type: string;
  object_name: string;
  volume: number;
  unit: string;
}

export interface LetterRequest {
  letter_type: 'запрос' | 'претензия' | 'уведомление' | 'ответ';
  addressee: string;
  subject: string;
  body_points: string[];
}

export interface KSWorkItem {
  name: string;
  unit: string;
  volume: number;
  norm_hours: number;
  price_per_unit: number;
}

export interface KSRequest {
  object_name: string;
  contract_number: string;
  period_from: string;
  period_to: string;
  work_items: KSWorkItem[];
}

export interface GenerateDocumentResponse {
  result?: string;
  text?: string;
  content?: string;
  document?: Record<string, unknown>;
  session_id?: string;
  [key: string]: unknown;
}

export interface ApiConfig {
  apiUrl: string;
  apiKey: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  uptime_seconds: number;
  components: Record<string, { status: string; [key: string]: unknown }>;
}

export interface ApiCallOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export const DEFAULT_API_URL = 'https://vanekpetrov1997.fvds.ru';

const LEGACY_DEFAULT_API_URL = 'http://vanekpetrov1997.fvds.ru';

export const normalizeApiUrl = (apiUrl: string) => {
  const trimmedUrl = apiUrl.trim().replace(/\/+$/, '');

  if (
    !trimmedUrl ||
    trimmedUrl === LEGACY_DEFAULT_API_URL ||
    trimmedUrl === 'http://vanekpetrov1997.fvds.ru'
  ) {
    return DEFAULT_API_URL;
  }

  return trimmedUrl;
};

async function postJson<TRequest>(
  apiUrl: string,
  apiKey: string,
  endpoint: string,
  payload: TRequest,
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<GenerateDocumentResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey.trim()
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });

  return (await response.json()) as GenerateDocumentResponse;
}

export async function getApiConfig(): Promise<ApiConfig> {
  const store = await Store.load('settings.json');
  const savedUrl = await store.get<string>('api_url');
  const fallbackUrl = (await invoke<string>('get_api_url')) || DEFAULT_API_URL;
  const apiUrl = normalizeApiUrl(savedUrl || fallbackUrl || DEFAULT_API_URL);
  const apiKey = ((await store.get<string>('api_key')) || '').trim();

  const isDev = Boolean((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV);
  if (isDev) {
    console.debug('[API] url=', apiUrl, 'keyLen=', apiKey.length);
  }

  return { apiUrl, apiKey };
}

export async function sendChatMessage(
  apiUrl: string,
  apiKey: string,
  payload: ChatRequest,
  { timeoutMs = DEFAULT_CHAT_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<ChatResponse> {
  const endpoint = '/api/chat';
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey.trim()
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });

  return (await response.json()) as ChatResponse;
}

export async function checkHealth(apiUrl: string, { timeoutMs, signal }: ApiCallOptions = {}): Promise<HealthResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/health', {
    timeoutMs,
    signal
  });
  return (await response.json()) as HealthResponse;
}

export function generateTK(apiUrl: string, apiKey: string, payload: TKRequest, options?: ApiCallOptions) {
  return postJson(apiUrl, apiKey, '/api/generate/tk', payload, options);
}

export function generateLetter(apiUrl: string, apiKey: string, payload: LetterRequest, options?: ApiCallOptions) {
  return postJson(apiUrl, apiKey, '/api/generate/letter', payload, options);
}

export function generateKS(apiUrl: string, apiKey: string, payload: KSRequest, options?: ApiCallOptions) {
  return postJson(apiUrl, apiKey, '/api/generate/ks', payload, options);
}

export async function downloadTKDocx(
  apiUrl: string,
  apiKey: string,
  sessionId: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<Blob> {
  const endpoint = `/api/generate/tk/${encodeURIComponent(sessionId)}/download`;
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });

  return await response.blob();
}

export async function downloadLetterDocx(
  apiUrl: string,
  apiKey: string,
  sessionId: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<Blob> {
  const endpoint = `/api/generate/letter/${encodeURIComponent(sessionId)}/download`;
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });

  return await response.blob();
}

export async function downloadKSDocx(
  apiUrl: string,
  apiKey: string,
  sessionId: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<Blob> {
  const endpoint = `/api/generate/ks/${encodeURIComponent(sessionId)}/download`;
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });

  return await response.blob();
}
