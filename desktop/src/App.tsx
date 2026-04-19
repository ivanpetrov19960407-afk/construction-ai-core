import { useEffect, useMemo, useState } from 'react';
import { checkHealth, fetchNotifications, getApiConfig, type DesktopNotification } from './api/coreClient';
import Sidebar from './components/Sidebar';
import StatusBar from './components/StatusBar';
import { resolveRoute } from './router';
import { colors, spacing, typography } from './styles/tokens';
import type { BrandingConfig } from './store/brandingStore';
import { useBrandingStore } from './store/brandingStore';
import { useServerStatusStore } from './store/serverStatusStore';

const normalizePath = (path: string) => path.replace(/\/$/, '') || '/';

const APP_THEME_BASE = {
  minHeight: '100vh',
  fontFamily: typography.fontFamily,
  display: 'flex',
  background: colors.bgPage,
  overflow: 'hidden'
} as const;

export default function App() {
  const [currentPath, setCurrentPath] = useState(() => normalizePath(window.location.pathname));
  const [toasts, setToasts] = useState<DesktopNotification[]>([]);
  const branding = useBrandingStore((state) => state.branding);
  const setBranding = useBrandingStore((state) => state.setBranding);

  useEffect(() => {
    const onPopState = () => setCurrentPath(normalizePath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    let isDisposed = false;

    const pollNotifications = async () => {
      try {
        const { apiUrl, apiKey } = await getApiConfig();
        const storageKey = 'desktop_user_id';
        const existingUserId = localStorage.getItem(storageKey);
        const userId = existingUserId || `desktop-${crypto.randomUUID()}`;
        if (!existingUserId) {
          localStorage.setItem(storageKey, userId);
        }
        if (!apiKey.trim()) {
          return;
        }
        const notifications = await fetchNotifications(apiUrl, apiKey, userId);
        if (isDisposed || notifications.length === 0) {
          return;
        }
        setToasts((prev) => [...prev, ...notifications].slice(-5));
      } catch (_error) {
        // ignore polling errors in MVP mode
      }
    };

    void pollNotifications();
    const intervalId = window.setInterval(() => {
      void pollNotifications();
    }, 15_000);

    return () => {
      isDisposed = true;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (toasts.length === 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setToasts((prev) => prev.slice(1));
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [toasts]);

  useEffect(() => {
    let isMounted = true;

    async function loadBranding(): Promise<void> {
      try {
        const { apiUrl, apiKey } = await getApiConfig();
        const response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/branding`, {
          method: 'GET',
          headers: {
            'X-API-Key': apiKey
          }
        });
        if (!response.ok) {
          return;
        }

        const data = (await response.json()) as BrandingConfig;
        if (isMounted) {
          setBranding(data);
        }
      } catch (_error) {
        // fallback to default UI theme
      }
    }

    void loadBranding();
    return () => {
      isMounted = false;
    };
  }, [setBranding]);

  useEffect(() => {
    let isDisposed = false;
    const { setChecking, setOnline, updateFromHealth } = useServerStatusStore.getState();

    const refreshServerStatus = async () => {
      setChecking(true);

      try {
        const { apiUrl } = await getApiConfig();
        const health = await checkHealth(apiUrl);
        if (isDisposed) {
          return;
        }
        updateFromHealth(health);
      } catch (_error) {
        if (isDisposed) {
          return;
        }
        setChecking(false);
        setOnline(false);
      }
    };

    void refreshServerStatus();
    const intervalId = window.setInterval(() => {
      void refreshServerStatus();
    }, 60_000);

    return () => {
      isDisposed = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const navigate = (path: string) => {
    const nextPath = normalizePath(path);
    if (nextPath === currentPath) {
      return;
    }

    window.history.pushState({}, '', nextPath);
    setCurrentPath(nextPath);
  };

  const appTheme = useMemo(
    () => ({
      ...APP_THEME_BASE,
      borderTop: `4px solid ${branding?.primary_color ?? '#2563eb'}`,
    }),
    [branding?.primary_color]
  );

  return (
    <>
      <style>{`*, *::before, *::after { box-sizing: border-box; } body { margin: 0; }`}</style>
      <main style={appTheme}>
        <Sidebar currentPath={currentPath} onNavigate={navigate} />
        <section style={{ flex: 1, padding: spacing.lg, paddingBottom: spacing.xxl }}>
          <div className="page-content" style={{ maxWidth: 920, width: '100%' }}>
            {resolveRoute(currentPath, () => navigate('/'))}
          </div>
        </section>
      </main>
      <StatusBar />
      <div style={{ position: 'fixed', right: spacing.lg, bottom: spacing.xl, zIndex: 1000, display: 'grid', gap: spacing.sm }}>
        {toasts.map((toast) => (
          <div
            key={toast.id}
            style={{
              minWidth: 280,
              maxWidth: 360,
              background: colors.bgCard,
              border: `1px solid ${colors.border}`,
              borderRadius: 10,
              boxShadow: '0 8px 28px rgba(2, 6, 23, 0.25)',
              padding: spacing.md
            }}
          >
            <strong style={{ display: 'block', marginBottom: spacing.xs }}>{toast.title}</strong>
            <span style={{ color: colors.textSecondary, fontSize: 13 }}>{toast.body}</span>
          </div>
        ))}
      </div>
    </>
  );
}
