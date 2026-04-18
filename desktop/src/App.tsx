import { useEffect, useMemo, useState } from 'react';
import { checkHealth, getApiConfig } from './api/coreClient';
import Sidebar from './components/Sidebar';
import StatusBar from './components/StatusBar';
import { resolveRoute } from './router';
import { colors, spacing, typography } from './styles/tokens';
import type { BrandingConfig } from './store/brandingStore';
import { useBrandingStore } from './store/brandingStore';
import { useServerStatusStore } from './store/serverStatusStore';

const normalizePath = (path: string) => path.replace(/\/$/, '') || '/';

export default function App() {
  const [currentPath, setCurrentPath] = useState(() => normalizePath(window.location.pathname));
  const branding = useBrandingStore((state) => state.branding);
  const setBranding = useBrandingStore((state) => state.setBranding);

  useEffect(() => {
    const onPopState = () => setCurrentPath(normalizePath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

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
      minHeight: '100vh',
      fontFamily: typography.fontFamily,
      display: 'flex',
      gap: spacing.lg,
      borderTop: `4px solid ${branding?.primary_color ?? '#2563eb'}`,
      background: colors.bgPage
    }),
    [branding?.primary_color]
  );

  return (
    <>
      <style>{`*, *::before, *::after { box-sizing: border-box; } body { margin: 0; }`}</style>
      <main style={appTheme}>
        <Sidebar currentPath={currentPath} onNavigate={navigate} />
        <section style={{ flex: 1, padding: spacing.lg, paddingBottom: 36 }}>
          {resolveRoute(currentPath, () => navigate('/'))}
        </section>
      </main>
      <StatusBar />
    </>
  );
}
