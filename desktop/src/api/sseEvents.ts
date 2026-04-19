import type { GenerateDocumentResponse } from './coreClient';

export type SSEEventName = 'progress' | 'chunk' | 'error' | 'done' | 'source';

export interface SSEEventBase {
  event: SSEEventName;
  progress?: number;
  stage?: string;
  message?: string;
}

export interface SSEProgressEvent extends SSEEventBase {
  event: 'progress';
}

export interface SSEChunkEvent extends SSEEventBase {
  event: 'chunk';
  chunk?: string;
}

export interface SSEErrorEvent extends SSEEventBase {
  event: 'error';
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface SSEDoneEvent extends SSEEventBase {
  event: 'done';
  result?: GenerateDocumentResponse;
}

export interface SSESourceEvent extends SSEEventBase {
  event: 'source';
  source?: {
    title: string;
    page: number;
    score: number;
  };
}

export type SSEEvent =
  | SSEProgressEvent
  | SSEChunkEvent
  | SSEErrorEvent
  | SSEDoneEvent
  | SSESourceEvent;

export function parseSSEEvent(raw: string): SSEEvent | null {
  const lines = raw
    .split('\n')
    .map((line) => line.trimEnd())
    .filter(Boolean);

  if (!lines.length) return null;

  const eventLine = lines.find((line) => line.startsWith('event:'));
  const dataLines = lines.filter((line) => line.startsWith('data:'));
  if (!eventLine || !dataLines.length) {
    return null;
  }

  const eventName = eventLine.replace(/^event:\s*/, '').trim();
  const dataRaw = dataLines.map((line) => line.replace(/^data:\s*/, '')).join('\n');
  const payload = JSON.parse(dataRaw) as Record<string, unknown>;

  if (eventName === 'error') {
    return {
      event: 'error',
      code: String(payload.code ?? 'internal'),
      message: String(payload.message ?? 'Ошибка генерации'),
      details:
        payload.details && typeof payload.details === 'object'
          ? (payload.details as Record<string, unknown>)
          : undefined,
      progress: typeof payload.progress === 'number' ? payload.progress : undefined,
      stage: typeof payload.stage === 'string' ? payload.stage : undefined,
    };
  }

  if (eventName === 'done') {
    return {
      event: 'done',
      result:
        payload.result && typeof payload.result === 'object'
          ? (payload.result as GenerateDocumentResponse)
          : undefined,
      progress: typeof payload.progress === 'number' ? payload.progress : undefined,
      stage: typeof payload.stage === 'string' ? payload.stage : undefined,
    };
  }

  if (eventName === 'chunk') {
    return {
      event: 'chunk',
      chunk: typeof payload.chunk === 'string' ? payload.chunk : undefined,
      progress: typeof payload.progress === 'number' ? payload.progress : undefined,
      stage: typeof payload.stage === 'string' ? payload.stage : undefined,
      message: typeof payload.message === 'string' ? payload.message : undefined,
    };
  }

  if (eventName === 'source') {
    const source = payload.source;
    if (
      source &&
      typeof source === 'object' &&
      typeof (source as Record<string, unknown>).title === 'string'
    ) {
      return {
        event: 'source',
        source: {
          title: String((source as Record<string, unknown>).title),
          page: Number((source as Record<string, unknown>).page ?? 0),
          score: Number((source as Record<string, unknown>).score ?? 0),
        },
      };
    }
    return { event: 'source' };
  }

  return {
    event: 'progress',
    progress: typeof payload.progress === 'number' ? payload.progress : undefined,
    stage: typeof payload.stage === 'string' ? payload.stage : eventName,
    message: typeof payload.message === 'string' ? payload.message : undefined,
  };
}
