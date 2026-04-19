export const DEFAULT_CHAT_TIMEOUT_MS = 120_000;
export const DEFAULT_GENERATION_TIMEOUT_MS = 300_000;

export type ApiErrorCode = 'timeout' | 'cancelled' | 'auth' | 'server' | 'http' | 'network';

export class ApiRequestError extends Error {
  code: ApiErrorCode;
  endpoint: string;
  status?: number;

  constructor(message: string, code: ApiErrorCode, endpoint: string, status?: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.endpoint = endpoint;
    this.status = status;
  }
}

interface ApiRequestOptions extends Omit<RequestInit, 'signal'> {
  timeoutMs?: number;
  signal?: AbortSignal;
}

function combineSignals(...signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const activeSignals = signals.filter((signal): signal is AbortSignal => Boolean(signal));
  if (!activeSignals.length) return undefined;

  const controller = new AbortController();

  const abort = () => {
    if (!controller.signal.aborted) {
      controller.abort();
    }
  };

  for (const signal of activeSignals) {
    if (signal.aborted) {
      abort();
      return controller.signal;
    }

    signal.addEventListener('abort', abort, { once: true });
  }

  return controller.signal;
}

async function readResponseBody(response: Response): Promise<string> {
  try {
    const text = await response.text();
    return text.trim() || '<пустой ответ>';
  } catch {
    return '<пустой ответ>';
  }
}

function formatNetworkMessage(endpoint: string, details?: string): string {
  const suffix = details ? ` Детали: ${details}` : '';
  return `Ошибка сети при обращении к ${endpoint}: проверьте интернет, API URL и доступность сервера.${suffix}`;
}

async function toHttpError(response: Response, endpoint: string): Promise<ApiRequestError> {
  const body = await readResponseBody(response);

  if (response.status === 401 || response.status === 403) {
    return new ApiRequestError(
      `Ошибка авторизации (${response.status}) для ${endpoint}. Проверьте API Key в настройках клиента и на сервере.`,
      'auth',
      endpoint,
      response.status
    );
  }

  if (response.status >= 500) {
    return new ApiRequestError(
      `Ошибка сервера (${response.status}) для ${endpoint}. Попробуйте повторить запрос позже. Ответ: ${body}`,
      'server',
      endpoint,
      response.status
    );
  }

  return new ApiRequestError(
    `HTTP ${response.status} для ${endpoint}. Ответ сервера: ${body}`,
    'http',
    endpoint,
    response.status
  );
}

export async function apiRequest(apiUrl: string, endpoint: string, options: ApiRequestOptions = {}): Promise<Response> {
  const { timeoutMs, signal, ...init } = options;
  const controller = new AbortController();
  const mergedSignal = combineSignals(signal, controller.signal);

  let timeoutId: number | null = null;
  let timedOut = false;

  if (typeof timeoutMs === 'number' && timeoutMs > 0) {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
  }

  try {
    const response = await fetch(`${apiUrl}${endpoint}`, {
      ...init,
      signal: mergedSignal
    });

    if (!response.ok) {
      throw await toHttpError(response, endpoint);
    }

    return response;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      if (timedOut) {
        throw new ApiRequestError(
          `Превышено время ожидания ответа (${Math.round((timeoutMs ?? 0) / 1000)} c) для ${endpoint}.`,
          'timeout',
          endpoint
        );
      }

      throw new ApiRequestError(`Запрос к ${endpoint} был отменён.`, 'cancelled', endpoint);
    }

    const details = error instanceof Error ? error.message : undefined;
    throw new ApiRequestError(formatNetworkMessage(endpoint, details), 'network', endpoint);
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}
