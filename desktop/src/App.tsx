import { useEffect, useMemo, useState } from 'react';
import { getApiConfig } from './api/coreClient';
import Sidebar from './components/Sidebar';
import { resolveRoute } from './router';
import type { BrandingConfig } from './store/brandingStore';
import { useBrandingStore } from './store/brandingStore';

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
      padding: 16,
      fontFamily: 'Inter, Arial, sans-serif',
      display: 'flex',
      gap: 16,
      borderTop: `4px solid ${branding?.primary_color ?? '#2563eb'}`
    }),
    [branding?.primary_color]
  );

  return (
    <main style={appTheme}>
      <Sidebar currentPath={currentPath} onNavigate={navigate} />
      <section style={{ flex: 1 }}>{resolveRoute(currentPath, () => navigate('/'))}</section>
    </main>
  );
}
