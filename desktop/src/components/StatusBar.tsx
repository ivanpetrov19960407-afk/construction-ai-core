import { useMemo } from 'react';
import { useChatStore, type ChatRole } from '../store/chatStore';
import { useServerStatusStore } from '../store/serverStatusStore';

const APP_VERSION =
  (import.meta as ImportMeta & { env?: { VITE_APP_VERSION?: string } }).env?.VITE_APP_VERSION || '0.5.0';

const ROLE_LABELS: Record<ChatRole, string> = {
  pto_engineer: 'ПТО-инженер',
  foreman: 'Прораб',
  tender_specialist: 'Тендерный специалист',
  admin: 'Администратор'
};

export default function StatusBar() {
  const role = useChatStore((state) => state.role);
  const { isOnline, isChecking, serverVersion } = useServerStatusStore((state) => ({
    isOnline: state.isOnline,
    isChecking: state.isChecking,
    serverVersion: state.serverVersion
  }));

  const status = useMemo(() => {
    if (isChecking) {
      return { text: 'Проверка...', color: '#f59e0b', blink: true };
    }

    if (isOnline) {
      return { text: 'OK', color: '#22c55e', blink: false };
    }

    return { text: 'Нет связи', color: '#ef4444', blink: false };
  }, [isChecking, isOnline]);

  return (
    <footer
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        height: 28,
        background: '#1e293b',
        color: '#ffffff',
        fontSize: 11,
        display: 'grid',
        gridTemplateColumns: '1fr auto 1fr',
        alignItems: 'center',
        padding: '0 12px',
        zIndex: 1000,
        borderTop: '1px solid rgba(255, 255, 255, 0.2)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            color: status.color,
            fontSize: 12,
            animation: status.blink ? 'statusbar-blink 1s ease-in-out infinite' : undefined
          }}
        >
          ●
        </span>
        <span>
          Сервер: <strong>{status.text}</strong>
        </span>
      </div>

      <div style={{ textAlign: 'center', opacity: 0.9 }}>
        app v{APP_VERSION} · server v{serverVersion || '—'}
      </div>

      <div style={{ justifySelf: 'end' }}>Роль: {ROLE_LABELS[role]}</div>

      <style>{`@keyframes statusbar-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }`}</style>
    </footer>
  );
}
