import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import {
  ApiRequestError,
  apiRequest,
  DEFAULT_CHAT_TIMEOUT_MS,
  DEFAULT_GENERATION_TIMEOUT_MS
} from '../lib/apiClient';
import type {
  AnalyticsSummaryResponse,
  AuthLoginRequest,
  AuthRegisterRequest,
  AuthTokenResponse,
  BillingQuotaResponse,
  ComplianceCheckRequest,
  ComplianceCheckResponse,
  ComplianceRule,
  GenerateEstimateRequest,
  GenerateExecAlbumRequest,
  GeneratePprRequest
} from '../types/api';
import type { ChatRole } from '../store/chatStore';
import { logError } from '../lib/logger';
import { parseSSEEvent } from './sseEvents';

export interface ChatRequest {
  message: string;
  role: ChatRole;
  session_id: string;
  message_id?: string;
}

export interface ChatSource {
  title: string;
  page: number;
  score: number;
}

export interface ChatResponse {
  reply: string;
  session_id?: string;
  agents_used?: string[];
  confidence?: number | null;
  conflict_rate?: number | null;
  sources?: ChatSource[];
  message_id?: string;
}

export interface ChatResponseMeta {
  agents?: string[];
  confidence?: number;
  sources?: ChatSource[];
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

export interface KSHeader {
  object_name: string;
  contract_number: string;
  period_from: string;
  period_to: string;
}

export interface KSWorkItemResult extends KSWorkItem {
  index: number;
  subtotal_cost: number;
  subtotal_hours: number;
}

export interface KS2Data extends Partial<KSHeader> {
  work_items: KSWorkItemResult[];
  total_cost: number;
  total_hours: number;
}

export interface KS3Data extends Partial<KSHeader> {
  period_days: number;
  total_cost: number;
  total_hours: number;
  workers_needed: number;
}

export interface KSGenerationResponse extends GenerateDocumentResponse {
  session_id: string;
  result: string;
  ks2: KS2Data;
  ks3: KS3Data;
  docx_bytes_key: string;
  total_cost: number;
  total_hours: number;
  sha256: string | null;
}

export interface GenerateDocumentResponse {
  result?: string;
  text?: string;
  content?: string;
  document?: Record<string, unknown>;
  session_id?: string;
  [key: string]: unknown;
}
export type GenerationStage = 'queued' | 'research' | 'draft' | 'critic' | 'verify' | 'format' | 'done' | 'error';

export interface GenerationStreamEvent {
  event: GenerationStage;
  stage: GenerationStage;
  progress: number;
  message?: string;
  code?: string;
  result?: GenerateDocumentResponse;
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
  llm: {
    default: string;
    available: string[];
    degraded: boolean;
  };
  components: Record<string, { status: string; [key: string]: unknown }>;
}

export interface ApiCallOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface UploadChatDocumentResponse {
  chunks_added: number;
  source: string;
}

export interface RagSourceItem {
  source: string;
  chunks: number;
}

export interface MeResponse {
  username: string;
  role: string;
  is_admin: boolean;
}

export interface MyProjectItem {
  id: string;
  short_id: number;
  name: string;
}


export class ForbiddenError extends Error {
  status = 403;

  constructor(message = 'Недостаточно прав. Войдите как admin или используйте “Мою базу”') {
    super(message);
    this.name = 'ForbiddenError';
  }
}
export class SSEError extends Error {
  code: string;
  details?: Record<string, unknown>;

  constructor(code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'SSEError';
    this.code = code;
    this.details = details;
  }
}


export interface TelegramLinkResponse {
  ok: boolean;
  telegram_user_id: string;
  user_id: string;
  session_id: string;
}

export interface DesktopNotification {
  id: string;
  user_id: string;
  telegram_user_id: string;
  session_id: string;
  event_type: string;
  title: string;
  body: string;
  created_at: string;
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

async function postForm(
  apiUrl: string,
  apiKey: string,
  endpoint: string,
  payload: FormData,
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<GenerateDocumentResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'POST',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    body: payload,
    timeoutMs,
    signal
  });

  return (await response.json()) as GenerateDocumentResponse;
}

function parseError(error: unknown): never {
  if (error instanceof ApiRequestError && error.status === 403) {
    throw new ForbiddenError();
  }

  if (error instanceof Error) {
    throw error;
  }

  throw new Error('Неизвестная ошибка запроса.');
}

async function postJsonSSE<TRequest>(
  apiUrl: string,
  apiKey: string,
  endpoint: string,
  payload: TRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<GenerateDocumentResponse> {
  const controller = new AbortController();
  const timeoutId =
    typeof timeoutMs === 'number' && timeoutMs > 0 ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }

  try {
    const response = await fetch(`${normalizeApiUrl(apiUrl)}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-API-Key': apiKey.trim()
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`SSE HTTP error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      while (buffer.includes('\n\n')) {
        const splitAt = buffer.indexOf('\n\n');
        const rawEvent = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + 2);

        const parsedEvent = parseSSEEvent(rawEvent);
        if (!parsedEvent) {
          continue;
        }

        if (parsedEvent.event === 'error') {
          logError('sse_error_event', {
            code: parsedEvent.code,
            message: parsedEvent.message,
            details: parsedEvent.details,
            endpoint
          });
          throw new SSEError(parsedEvent.code, parsedEvent.message, parsedEvent.details);
        }

        const stage = (parsedEvent.stage ?? parsedEvent.event) as GenerationStage;
        onEvent({
          event: stage,
          stage,
          progress: parsedEvent.progress ?? 0,
          message: parsedEvent.message
        });

        if (parsedEvent.event === 'done' && parsedEvent.result) {
          return parsedEvent.result;
        }
      }
    }
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
  }

  throw new SSEError('internal', 'Поток генерации завершился без результата');
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

export async function sendChatMessageStream(
  apiUrl: string,
  apiKey: string,
  payload: ChatRequest,
  onEvent: (event: import('./sseEvents').SSEEvent) => void,
  { timeoutMs = DEFAULT_CHAT_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<ChatResponse> {
  const controller = new AbortController();
  const timeoutId =
    typeof timeoutMs === 'number' && timeoutMs > 0 ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }

  try {
    const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/chat?stream=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-API-Key': apiKey.trim()
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`SSE HTTP error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      while (buffer.includes('\n\n')) {
        const splitAt = buffer.indexOf('\n\n');
        const rawEvent = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + 2);

        const parsedEvent = parseSSEEvent(rawEvent);
        if (!parsedEvent) continue;
        onEvent(parsedEvent);

        if (parsedEvent.event === 'error') {
          throw new SSEError(parsedEvent.code, parsedEvent.message, parsedEvent.details);
        }
        if (parsedEvent.event === 'done' && parsedEvent.result) {
          return parsedEvent.result as unknown as ChatResponse;
        }
      }
    }
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
  }

  throw new SSEError('internal', 'Поток чата завершился без результата');
}

export async function uploadChatDocument(
  apiUrl: string,
  apiKey: string,
  payload: {
    file: File;
    sessionId: string;
  },
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<UploadChatDocumentResponse> {
  try {
    const endpoint = '/api/rag/chat-upload';
    const formData = new FormData();
    formData.append('file', payload.file, payload.file.name);
    formData.append('source_name', payload.file.name);
    formData.append('session_id', payload.sessionId);

    const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
      method: 'POST',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      body: formData,
      timeoutMs,
      signal
    });

    return (await response.json()) as UploadChatDocumentResponse;
  } catch (error) {
    parseError(error);
  }
}

export async function ingestGlobal(
  apiUrl: string,
  apiKey: string,
  payload: {
    file: File;
    sourceName?: string;
  },
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<UploadChatDocumentResponse> {
  try {
    const endpoint = '/api/rag/ingest';
    const formData = new FormData();
    formData.append('file', payload.file, payload.file.name);
    formData.append('source_name', payload.sourceName || payload.file.name);

    const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
      method: 'POST',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      body: formData,
      timeoutMs,
      signal
    });
    return (await response.json()) as UploadChatDocumentResponse;
  } catch (error) {
    parseError(error);
  }
}

export async function listMySources(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<RagSourceItem[]> {
  try {
    const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/rag/my-sources', {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      timeoutMs,
      signal
    });
    const payload = (await response.json()) as { sources?: RagSourceItem[] };
    return Array.isArray(payload.sources) ? payload.sources : [];
  } catch (error) {
    parseError(error);
  }
}

export async function listGlobalSources(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<RagSourceItem[]> {
  try {
    const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/rag/sources', {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      timeoutMs,
      signal
    });
    const payload = (await response.json()) as { sources?: RagSourceItem[] };
    return Array.isArray(payload.sources) ? payload.sources : [];
  } catch (error) {
    parseError(error);
  }
}

export async function deleteGlobalSource(
  apiUrl: string,
  apiKey: string,
  source: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<{ deleted: number; source: string }> {
  try {
    const endpoint = `/api/rag/sources/${encodeURIComponent(source)}`;
    const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
      method: 'DELETE',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      timeoutMs,
      signal
    });
    return (await response.json()) as { deleted: number; source: string };
  } catch (error) {
    parseError(error);
  }
}

export async function getMe(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<MeResponse> {
  try {
    const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/me', {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      timeoutMs,
      signal
    });
    return (await response.json()) as MeResponse;
  } catch (error) {
    parseError(error);
  }
}


export async function listMyProjects(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<MyProjectItem[]> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/projects/mine', {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });
  const payload = (await response.json()) as { projects?: MyProjectItem[] };
  return Array.isArray(payload.projects) ? payload.projects : [];
}

export async function checkHealth(apiUrl: string, { timeoutMs, signal }: ApiCallOptions = {}): Promise<HealthResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/health', {
    timeoutMs,
    signal
  });
  return (await response.json()) as HealthResponse;
}

export async function linkTelegramAccount(
  apiUrl: string,
  apiKey: string,
  payload: { code: string; user_id: string; session_id: string },
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<TelegramLinkResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/link/telegram', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey.trim()
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });
  return (await response.json()) as TelegramLinkResponse;
}

export async function fetchNotifications(
  apiUrl: string,
  apiKey: string,
  userId: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<DesktopNotification[]> {
  const endpoint = `/api/notifications?user_id=${encodeURIComponent(userId)}`;
  const response = await apiRequest(normalizeApiUrl(apiUrl), endpoint, {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });
  const data = (await response.json()) as { notifications?: DesktopNotification[] };
  return Array.isArray(data.notifications) ? data.notifications : [];
}

export function generateTK(apiUrl: string, apiKey: string, payload: TKRequest, options?: ApiCallOptions) {
  return postJson(apiUrl, apiKey, '/api/generate/tk', payload, options);
}
export function generateTKStream(
  apiUrl: string,
  apiKey: string,
  payload: TKRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/tk?stream=true', payload, onEvent, options);
}

export function generateLetter(
  apiUrl: string,
  apiKey: string,
  payload: LetterRequest,
  options?: ApiCallOptions
) {
  return postJson(apiUrl, apiKey, '/api/generate/letter', payload, options);
}

export function generateLetterStream(
  apiUrl: string,
  apiKey: string,
  payload: LetterRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/letter?stream=true', payload, onEvent, options);
}

export function generateKS(apiUrl: string, apiKey: string, payload: KSRequest, options?: ApiCallOptions) {
  return postJson(apiUrl, apiKey, '/api/generate/ks', payload, options) as Promise<KSGenerationResponse>;
}
export function generateKSStream(
  apiUrl: string,
  apiKey: string,
  payload: KSRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/ks?stream=true', payload, onEvent, options) as Promise<KSGenerationResponse>;
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

export function generatePpr(
  apiUrl: string,
  apiKey: string,
  payload: GeneratePprRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/ppr?stream=true', payload, onEvent, options);
}

export function generateEstimate(
  apiUrl: string,
  apiKey: string,
  payload: GenerateEstimateRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/estimate?stream=true', payload, onEvent, options);
}

export async function analyzeDocument(
  apiUrl: string,
  apiKey: string,
  file: File,
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
) {
  const form = new FormData();
  form.append('file', file, file.name);
  return postForm(apiUrl, apiKey, '/api/analyze/document', form, { timeoutMs, signal });
}

export function generateExecAlbum(
  apiUrl: string,
  apiKey: string,
  payload: GenerateExecAlbumRequest,
  onEvent: (event: GenerationStreamEvent) => void,
  options?: ApiCallOptions
) {
  return postJsonSSE(apiUrl, apiKey, '/api/generate/exec-album?stream=true', payload, onEvent, options);
}

export async function getAnalyticsSummary(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<AnalyticsSummaryResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/analytics/summary', {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });
  return (await response.json()) as AnalyticsSummaryResponse;
}

export async function listCompliance(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<ComplianceRule[]> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/compliance/rules', {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });
  const payload = (await response.json()) as { items?: ComplianceRule[]; rules?: ComplianceRule[] };
  return Array.isArray(payload.items) ? payload.items : Array.isArray(payload.rules) ? payload.rules : [];
}

export async function checkCompliance(
  apiUrl: string,
  apiKey: string,
  payload: ComplianceCheckRequest,
  { timeoutMs = DEFAULT_GENERATION_TIMEOUT_MS, signal }: ApiCallOptions = {}
): Promise<ComplianceCheckResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/compliance/check', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey.trim()
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });
  return (await response.json()) as ComplianceCheckResponse;
}

export async function login(
  apiUrl: string,
  payload: AuthLoginRequest,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<AuthTokenResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });
  return (await response.json()) as AuthTokenResponse;
}

export async function register(
  apiUrl: string,
  payload: AuthRegisterRequest,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<AuthTokenResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/auth/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload),
    timeoutMs,
    signal
  });
  return (await response.json()) as AuthTokenResponse;
}

export async function getQuotas(
  apiUrl: string,
  apiKey: string,
  { timeoutMs, signal }: ApiCallOptions = {}
): Promise<BillingQuotaResponse> {
  const response = await apiRequest(normalizeApiUrl(apiUrl), '/api/billing/quotas', {
    method: 'GET',
    headers: {
      'X-API-Key': apiKey.trim()
    },
    timeoutMs,
    signal
  });
  return (await response.json()) as BillingQuotaResponse;
}
