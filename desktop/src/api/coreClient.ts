import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import type { ChatRole } from '../store/chatStore';

export interface ChatRequest {
  message: string;
  role: ChatRole;
  session_id: string;
}

export interface ChatResponse {
  reply: string;
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

const normalizeApiUrl = (apiUrl: string) => apiUrl.replace(/\/$/, '');

async function postJson<TRequest>(
  apiUrl: string,
  apiKey: string,
  endpoint: string,
  payload: TRequest
): Promise<GenerateDocumentResponse> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return (await response.json()) as GenerateDocumentResponse;
}

export async function getApiConfig(): Promise<ApiConfig> {
  const store = await Store.load('settings.json');
  const savedUrl = await store.get<string>('api_url');
  const apiUrl = savedUrl || (await invoke<string>('get_api_url'));
  const apiKey = (await store.get<string>('api_key')) || '';
  return { apiUrl, apiKey };
}

export async function sendChatMessage(
  apiUrl: string,
  apiKey: string,
  payload: ChatRequest
): Promise<ChatResponse> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}

export function generateTK(apiUrl: string, apiKey: string, payload: TKRequest) {
  return postJson(apiUrl, apiKey, '/api/generate/tk', payload);
}

export function generateLetter(apiUrl: string, apiKey: string, payload: LetterRequest) {
  return postJson(apiUrl, apiKey, '/api/generate/letter', payload);
}

export function generateKS(apiUrl: string, apiKey: string, payload: KSRequest) {
  return postJson(apiUrl, apiKey, '/api/generate/ks', payload);
}

export async function downloadTKDocx(apiUrl: string, apiKey: string, sessionId: string): Promise<Blob> {
  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/api/generate/tk/${encodeURIComponent(sessionId)}/download`,
    {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey
      }
    }
  );

  if (!response.ok) {
    throw new Error(`Download API error: ${response.status}`);
  }

  return await response.blob();
}
