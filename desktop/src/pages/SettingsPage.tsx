import { FormEvent, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import {
  DEFAULT_API_URL,
  checkHealth,
  linkTelegramAccount,
  normalizeApiUrl,
  type HealthResponse,
} from '../api/coreClient';
import { useChatStore, type ChatRole } from '../store/chatStore';
import { useServerStatusStore } from '../store/serverStatusStore';
import { useAuth } from '../context/AuthContext';

type ConnectionStatus = {
  tone: 'idle' | 'checking' | 'success' | 'warning' | 'error';
  message: string;
};

const statusColor: Record<ConnectionStatus['tone'], string> = {
  idle: colors.textSecondary,
  checking: colors.primary,
  success: colors.success,
  warning: colors.warning,
  error: colors.error,
};

const ROLE_OPTIONS: Array<{ value: ChatRole; label: string }> = [
  { value: 'pto_engineer', label: 'ПТО-инженер' },
  { value: 'foreman', label: 'Прораб' },
  { value: 'tender_specialist', label: 'Тендерный специалист' },
  { value: 'admin', label: 'Администратор' },
];

const COMPONENT_LABELS: Record<string, string> = {
  database: 'База данных',
  rag_engine: 'RAG движок',
  llm_router: 'LLM роутер',
  telegram_webhook: 'Telegram',
};

const APP_VERSION =
  (import.meta as ImportMeta & { env?: { VITE_APP_VERSION?: string } }).env?.VITE_APP_VERSION ||
  '0.5.0';

export default function SettingsPage() {
  const { me, isAdmin } = useAuth();
  const setDefaultRole = useChatStore((state) => state.setDefaultRole);
  const documentsCount = useServerStatusStore((state) => state.documentsCount);
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [apiKey, setApiKey] = useState('');
  const [defaultRole, setDefaultRoleValue] = useState<ChatRole>('pto_engineer');
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [telegramCode, setTelegramCode] = useState('');
  const [linkStatus, setLinkStatus] = useState('');
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    tone: 'idle',
    message: 'Проверка соединения ещё не выполнялась.',
  });

  useEffect(() => {
    const load = async () => {
      const store = await Store.load('settings.json');
      const url = normalizeApiUrl(
        (await store.get<string>('api_url')) ||
          (await invoke<string>('get_api_url')) ||
          DEFAULT_API_URL,
      );
      const key = (await store.get<string>('api_key')) || '';
      const storedDefaultRole = (await store.get<ChatRole>('default_role')) || 'pto_engineer';
      setApiUrl(url);
      setApiKey(key);
      setDefaultRoleValue(storedDefaultRole);
    };

    void load();
  }, []);

  const persistSettings = async (
    normalizedUrl: string,
    trimmedKey: string,
    nextDefaultRole: ChatRole,
  ) => {
    const store = await Store.load('settings.json');
    await store.set('api_url', normalizedUrl);
    await store.set('api_key', trimmedKey);
    await store.set('default_role', nextDefaultRole);
    await store.save();
    await invoke('set_api_url', { url: normalizedUrl });
    window.dispatchEvent(new Event('auth:credentials-changed'));
  };

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedUrl = normalizeApiUrl(apiUrl);
    const trimmedKey = apiKey.trim();

    try {
      await persistSettings(normalizedUrl, trimmedKey, defaultRole);
      setApiUrl(normalizedUrl);
      setApiKey(trimmedKey);
      setDefaultRole(defaultRole);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (error) {
      setConnectionStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Не удалось сохранить настройки API.',
      });
    }
  };

  const onCheckConnection = async () => {
    const normalizedUrl = normalizeApiUrl(apiUrl);
    const trimmedKey = apiKey.trim();
    setApiUrl(normalizedUrl);
    setConnectionStatus({ tone: 'checking', message: 'Проверяю сервер...' });

    try {
      // Шаг 1: проверить доступность сервера через /health (не требует ключа)
      const healthResponse = await checkHealth(normalizedUrl);
      setHealth(healthResponse);
      setLastCheckedAt(new Date().toISOString());

      if (!trimmedKey) {
        setConnectionStatus({
          tone: 'warning',
          message:
            'Сервер доступен, но API Key пустой. Для Chat и генерации документов укажите ключ из API_KEYS в серверном .env.',
        });
        return;
      }

      // Шаг 2: проверить ключ через POST /api/chat с минимальным запросом
      setConnectionStatus({ tone: 'checking', message: 'Сервер доступен. Проверяю API Key...' });
      const testResponse = await fetch(`${normalizedUrl}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': trimmedKey,
        },
        body: JSON.stringify({
          message: 'ping',
          role: 'pto_engineer',
          session_id: 'settings-check',
        }),
        signal: AbortSignal.timeout(10000),
      });

      // 200 или 422 (validation error) — оба означают что ключ принят
      // 401/403 — ключ неверный
      if (testResponse.status === 401 || testResponse.status === 403) {
        setConnectionStatus({
          tone: 'error',
          message: `Неверный API Key (HTTP ${testResponse.status}). Проверьте значение API_KEYS в .env на сервере.`,
        });
        return;
      }

      // Ключ принят — сохранить настройки
      await persistSettings(normalizedUrl, trimmedKey, defaultRole);
      setApiKey(trimmedKey);
      setDefaultRole(defaultRole);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);

      setConnectionStatus({
        tone: 'success',
        message: 'Сервер доступен, API Key принят. Desktop готов к работе с серверным API.',
      });
    } catch (error) {
      setHealth(null);
      setLastCheckedAt(new Date().toISOString());
      setConnectionStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Не удалось проверить соединение с API.',
      });
    }
  };

  const onLinkTelegram = async () => {
    const normalizedUrl = normalizeApiUrl(apiUrl);
    const trimmedKey = apiKey.trim();
    const code = telegramCode.trim();
    if (!code) {
      setLinkStatus('Введите код из Telegram-бота (/link).');
      return;
    }
    if (!trimmedKey) {
      setLinkStatus('Сначала заполните API Key.');
      return;
    }
    const storageKey = 'desktop_user_id';
    const existingUserId = localStorage.getItem(storageKey);
    const userId = existingUserId || `desktop-${crypto.randomUUID()}`;
    if (!existingUserId) {
      localStorage.setItem(storageKey, userId);
    }
    const desktopSessionId = useChatStore.getState().sessionId;

    try {
      await linkTelegramAccount(normalizedUrl, trimmedKey, {
        code,
        user_id: userId,
        session_id: desktopSessionId,
      });
      setLinkStatus('Telegram успешно привязан. Уведомления теперь будут приходить в desktop.');
      setTelegramCode('');
    } catch (error) {
      setLinkStatus(error instanceof Error ? error.message : 'Не удалось привязать Telegram.');
    }
  };

  const openKnowledgeBase = () => {
    window.history.pushState({}, '', '/knowledge-base');
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  return (
    <Card>
      <form onSubmit={onSave} style={{ display: 'grid', gap: spacing.md, maxWidth: 640 }}>
        <p style={{ margin: 0, color: colors.textSecondary }}>
          Текущая роль: {isAdmin ? 'Администратор' : (me?.role ?? 'не определена')}
        </p>
        <Input label="API URL" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} />
        <Input label="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        <Input
          label="Код привязки из Telegram (/link)"
          value={telegramCode}
          onChange={(e) => setTelegramCode(e.target.value)}
          placeholder="Вставьте токен из бота"
        />
        <label style={{ display: 'grid', gap: spacing.xs }}>
          <span style={{ color: colors.textPrimary, fontWeight: 500 }}>Имя роли по умолчанию</span>
          <select
            value={defaultRole}
            onChange={(event) => setDefaultRoleValue(event.target.value as ChatRole)}
            style={{
              border: `1px solid ${colors.border}`,
              borderRadius: 8,
              padding: `${spacing.sm}px ${spacing.md}px`,
              color: colors.textPrimary,
            }}
          >
            {ROLE_OPTIONS.map((roleOption) => (
              <option key={roleOption.value} value={roleOption.value}>
                {roleOption.label}
              </option>
            ))}
          </select>
        </label>
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
          <Button type="button" variant="secondary" onClick={onLinkTelegram}>
            Привязать Telegram
          </Button>
        </div>
        {saved && <span style={{ color: colors.success }}>Сохранено ✓</span>}
        <p style={{ color: statusColor[connectionStatus.tone], margin: 0 }}>
          {connectionStatus.message}
        </p>
        {linkStatus && <p style={{ margin: 0, color: colors.textSecondary }}>{linkStatus}</p>}

        {documentsCount === 0 && (
          <Card
            padding="md"
            style={{
              border: `1px solid ${colors.warning}`,
              backgroundColor: `${colors.warning}14`,
            }}
          >
            <p
              style={{
                marginTop: 0,
                marginBottom: spacing.sm,
                color: colors.warning,
                fontWeight: 600,
              }}
            >
              Нормативы не загружены — качество ответов снижено.
            </p>
            <p style={{ marginTop: 0, marginBottom: spacing.sm, color: colors.textPrimary }}>
              Чтобы улучшить ответы, добавьте PDF в Базу знаний:
            </p>
            <ol
              style={{
                marginTop: 0,
                marginBottom: spacing.md,
                paddingLeft: spacing.lg,
                color: colors.textPrimary,
              }}
            >
              <li>Откройте раздел «База знаний».</li>
              <li>Нажмите «Загрузить PDF» и выберите файл с нормативами (СП, ГОСТ).</li>
              <li>Дождитесь сообщения об успешной загрузке и вернитесь в чат.</li>
            </ol>
            <Button type="button" variant="secondary" onClick={openKnowledgeBase}>
              Перейти в Базу знаний
            </Button>
          </Card>
        )}
      </form>
      {health && (
        <Card padding="md" style={{ marginTop: spacing.lg }}>
          <h3 style={{ marginTop: 0, marginBottom: spacing.sm }}>Статус сервера</h3>
          <p style={{ marginTop: 0 }}>
            {health.service} — {health.status}
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}` }}>
                  Компонент
                </th>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}` }}>
                  Статус
                </th>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}` }}>
                  Детали
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(health.components).map(([key, component]) => {
                const statusIcon =
                  component.status === 'ok' || component.status === 'active' ? '✅' : '⚠️';
                const details =
                  key === 'rag_engine'
                    ? `${String(component.sources ?? 0)} документов`
                    : key === 'llm_router' && component.provider
                      ? String(component.provider)
                      : '-';

                return (
                  <tr key={key}>
                    <td style={{ paddingTop: spacing.xs }}>{COMPONENT_LABELS[key] || key}</td>
                    <td style={{ paddingTop: spacing.xs }}>
                      {statusIcon} {component.status}
                    </td>
                    <td style={{ paddingTop: spacing.xs }}>{details}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {(health.components.rag_engine?.sources as number | undefined) === 0 && (
            <p style={{ marginBottom: 0, color: colors.warning }}>
              Нормативы (СП, ГОСТ) не загружены — качество ответов снижено.
            </p>
          )}
        </Card>
      )}
      <Card padding="md" style={{ marginTop: spacing.lg }}>
        <h3 style={{ marginTop: 0, marginBottom: spacing.sm }}>Информация</h3>
        <p style={{ margin: 0 }}>Версия десктоп-приложения: {APP_VERSION}</p>
        <p style={{ margin: 0 }}>Версия сервера: {health?.version || 'не определена'}</p>
        <p style={{ margin: 0 }}>
          Дата последней проверки соединения:{' '}
          {lastCheckedAt ? new Date(lastCheckedAt).toLocaleString('ru-RU') : 'ещё не выполнялась'}
        </p>
      </Card>
    </Card>
  );
}
