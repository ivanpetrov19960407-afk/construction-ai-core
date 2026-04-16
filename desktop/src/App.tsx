import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import { resolveRoute } from './router';

const normalizePath = (path: string) => path.replace(/\/$/, '') || '/';

export default function App() {
  const [currentPath, setCurrentPath] = useState(() => normalizePath(window.location.pathname));

  useEffect(() => {
    const onPopState = () => setCurrentPath(normalizePath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigate = (path: string) => {
    const nextPath = normalizePath(path);
    if (nextPath === currentPath) {
      return;
    }

    window.history.pushState({}, '', nextPath);
    setCurrentPath(nextPath);
  };

  return (
    <main
      style={{
        minHeight: '100vh',
        padding: 16,
        fontFamily: 'Inter, Arial, sans-serif',
        display: 'flex',
        gap: 16
      }}
    >
      <Sidebar currentPath={currentPath} onNavigate={navigate} />
      <section style={{ flex: 1 }}>{resolveRoute(currentPath, () => navigate('/'))}</section>
    </main>
  );
}
