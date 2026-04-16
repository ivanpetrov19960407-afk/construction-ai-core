import type { ReactNode } from 'react';
import ChatPage from './pages/ChatPage';
import GenerateKSPage from './pages/GenerateKSPage';
import GenerateLetterPage from './pages/GenerateLetterPage';
import GenerateTKPage from './pages/GenerateTKPage';
import HandoverPage from './pages/HandoverPage';
import SettingsPage from './pages/SettingsPage';

export function resolveRoute(path: string, onNavigateHome: () => void): ReactNode {
  switch (path) {
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
    case '/handover':
      return <HandoverPage />;
    default:
      return (
        <section>
          <h2>Страница не найдена</h2>
          <button onClick={onNavigateHome}>На главную</button>
        </section>
      );
  }
}
