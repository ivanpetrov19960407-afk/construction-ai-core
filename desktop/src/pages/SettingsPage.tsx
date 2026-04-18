import { FormEvent, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import { DEFAULT_API_URL, apiFetch, assertOk, normalizeApiUrl } from '../api/coreClient';

type ConnectionStatus = {
  tone: 'idle' | 'checking' | 'success' | 'warning' | 'error';
  message: string;
};

const statusColor: Record<ConnectionStatus['tone'], string> = {
  idle: colors.textSecondary,
  checking: colors.primary,
  success: colors.success,
  warning: colors.warning,
  error: colors.error
};

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    tone: 'idle',
    message: 'Проверка соединения ещё не выполнялась.'
  });

  useEffect(() => {
    const load = async () => {
      const store = await Store.load('settings.json');
      const url = normalizeApiUrl(
        (await store.get<string>('api_url')) || (await invoke<string>('get_api_url')) || DEFAULT_API_URL
      );
      const key = (await store.get<string>('api_key')) || '';
      setApiUrl(url);
      setApiKey(key);
    };

    void load();
  }, []);

  const persistSettings = async (normalizedUrl: string, trimmedKey: string) => {
    const store = await Store.load('settings.json');
    await store.set('api_url', normalizedUrl);
    await store.set('api_key', trimmedKey);
    await store.save();
    await invoke('set_api_url', { url: normalizedUrl });
  };

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedUrl = normalizeApiUrl(apiUrl);
    const trimmedKey = apiKey.trim();

    try {
      await persistSettings(normalizedUrl, trimmedKey);
      setApiUrl(normalizedUrl);
      setApiKey(trimmedKey);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (error) {
      setConnectionStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Не удалось сохранить настройки API.'
      });
    }
  };

  const onCheckConnection = async () => {
    const normalizedUrl = normalizeApiUrl(apiUrl);
    const trimmedKey = apiKey.trim();
    setApiUrl(normalizedUrl);
    setConnectionStatus({ tone: 'checking', message: 'Проверяю сервер...' });

    try {
      const healthResponse = await apiFetch(normalizedUrl, '/health');
      await assertOk(healthResponse, '/health');

      if (!trimmedKey) {
        setConnectionStatus({
          tone: 'warning',
          message:
            'Сервер доступен, но API Key пустой. Для Chat и генерации документов укажите ключ из API_KEYS в серверном .env.'
        });
        return;
      }

      setConnectionStatus({ tone: 'checking', message: 'Сервер доступен. Проверяю API Key...' });
      const protectedResponse = await apiFetch(normalizedUrl, '/api/billing/plan', {
        method: 'GET',
        headers: {
          'X-API-Key': trimmedKey
        }
      });
      await assertOk(protectedResponse, '/api/billing/plan');
      await persistSettings(normalizedUrl, trimmedKey);
      setApiKey(trimmedKey);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);

      setConnectionStatus({
        tone: 'success',
        message: 'Сервер доступен, API Key принят. Desktop готов к работе с серверным API.'
      });
    } catch (error) {
      setConnectionStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Не удалось проверить соединение с API.'
      });
    }
  };

  return (
    <Card>
      <form onSubmit={onSave} style={{ display: 'grid', gap: spacing.md, maxWidth: 640 }}>
        <Input label="API URL" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} />
        <Input label="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        <div style={{ display: 'flex', gap: spacing.sm, flexWrap: 'wrap' }}>
          <Button type="submit">Сохранить</Button>
          <Button
            type="button"
            variant="secondary"
            onClick={onCheckConnection}
            disabled={connectionStatus.tone === 'checking'}
            loading={connectionStatus.tone === 'checking'}
          >
            {connectionStatus.tone === 'checking' ? 'Проверка...' : 'Проверить соединение'}
          </Button>
        </div>
        {saved && <span style={{ color: colors.success }}>Сохранено</span>}
        <p style={{ color: statusColor[connectionStatus.tone], margin: 0 }}>
          {connectionStatus.message}
        </p>
      </form>
    </Card>
  );
}
