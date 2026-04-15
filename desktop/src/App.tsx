import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import GenerateKSPage from './pages/GenerateKSPage';
import GenerateLetterPage from './pages/GenerateLetterPage';
import GenerateTKPage from './pages/GenerateTKPage';
import SettingsPage from './pages/SettingsPage';

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

  const renderPage = () => {
    switch (currentPath) {
      case '/':
        return <ChatPage />;
      case '/settings':
        return <SettingsPage />;
      case '/generate/tk':
        return <GenerateTKPage />;
      case '/generate/letter':
        return <GenerateLetterPage />;
      case '/generate/ks':
        return <GenerateKSPage />;
      default:
        return (
          <section>
            <h2>Страница не найдена</h2>
            <button onClick={() => navigate('/')}>На главную</button>
          </section>
        );
    }
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
      <section style={{ flex: 1 }}>{renderPage()}</section>
    </main>
  );
}
