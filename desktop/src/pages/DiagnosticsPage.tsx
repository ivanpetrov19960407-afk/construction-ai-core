import { useCallback, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import { checkHealth, DEFAULT_API_URL, normalizeApiUrl, type HealthResponse } from '../api/coreClient';
import { colors, spacing } from '../styles/tokens';

type HealthTone = 'idle' | 'checking' | 'ok' | 'error';

const toneColor: Record<HealthTone, string> = {
  idle: colors.textSecondary,
  checking: colors.primary,
  ok: colors.success,
  error: colors.error
};

export default function DiagnosticsPage() {
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthTone, setHealthTone] = useState<HealthTone>('idle');
  const [healthMessage, setHealthMessage] = useState('Проверка /health ещё не запускалась.');
  const [copyMessage, setCopyMessage] = useState('');

  const loadApiUrl = useCallback(async () => {
    const store = await Store.load('settings.json');
    const storedUrl = (await store.get<string>('api_url')) || (await invoke<string>('get_api_url')) || DEFAULT_API_URL;
    const normalized = normalizeApiUrl(storedUrl);
    setApiUrl(normalized);
    return normalized;
  }, []);

  const refreshHealth = useCallback(async () => {
    setHealthTone('checking');
    setHealthMessage('Проверяю /health...');

    try {
      const normalizedUrl = await loadApiUrl();
      const response = await checkHealth(normalizedUrl);
      setHealth(response);
      setHealthTone('ok');
      setHealthMessage(`Сервер доступен: ${response.status}`);
    } catch (error) {
      setHealth(null);
      setHealthTone('error');
      setHealthMessage(error instanceof Error ? error.message : 'Ошибка при проверке /health.');
    }
  }, [loadApiUrl]);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  const onOpenLogsFolder = async () => {
    try {
      await invoke('open_logs_folder');
    } catch (error) {
      setCopyMessage(error instanceof Error ? error.message : 'Не удалось открыть папку логов.');
    }
  };

  const onCopyLastLines = async () => {
    try {
      const lines = await invoke<string>('copy_last_log_lines', { lines: 200 });
      await navigator.clipboard.writeText(lines || 'Лог-файл пока пуст.');
      setCopyMessage('Скопировано: последние 200 строк app.log');
    } catch (error) {
      setCopyMessage(error instanceof Error ? error.message : 'Не удалось скопировать лог.');
    }
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Диагностика</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>
        Страница помогает проверить стабильность логирования и доступность API.
      </p>

      <Card padding="md" style={{ marginBottom: spacing.md }}>
        <p style={{ margin: 0 }}>
          <strong>Текущий API URL:</strong> {apiUrl}
        </p>
        <p style={{ marginBottom: 0, color: toneColor[healthTone] }}>
          <strong>/health:</strong> {healthMessage}
        </p>
        {health && (
          <p style={{ marginBottom: spacing.xs }}>
            Версия сервера: {health.version} · uptime: {Math.round(health.uptime_seconds)}s
          </p>
        )}
        {health && (
          <div style={{ marginTop: spacing.xs }}>
            <p style={{ marginTop: 0, marginBottom: spacing.xs }}>
              <strong>LLM-провайдеры</strong>
            </p>
            <p
              style={{
                marginTop: 0,
                marginBottom: spacing.xs,
                color: health.llm.degraded ? colors.error : colors.success
              }}
            >
              default: {health.llm.default}
              {health.llm.degraded ? ' (не настроен)' : ' (настроен)'}
            </p>
            <p style={{ marginTop: 0, marginBottom: 0, color: colors.textSecondary }}>
              available: {health.llm.available.length ? health.llm.available.join(', ') : 'нет'}
            </p>
          </div>
        )}
      </Card>

      <div style={{ display: 'flex', gap: spacing.sm, flexWrap: 'wrap' }}>
        <Button type="button" onClick={onOpenLogsFolder}>
          Открыть папку логов
        </Button>
        <Button type="button" variant="secondary" onClick={onCopyLastLines}>
          Скопировать последние 200 строк
        </Button>
        <Button type="button" variant="ghost" onClick={() => void refreshHealth()} loading={healthTone === 'checking'}>
          {healthTone === 'checking' ? 'Проверка...' : 'Обновить /health'}
        </Button>
      </div>

      {copyMessage && (
        <p style={{ marginTop: spacing.md, marginBottom: 0, color: colors.textSecondary }}>
          {copyMessage}
        </p>
      )}
    </Card>
  );
}
