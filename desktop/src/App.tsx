import { useState } from 'react';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  const [page, setPage] = useState<'chat' | 'settings'>('chat');

  return (
    <main style={{ minHeight: '100vh', padding: 16, fontFamily: 'Inter, Arial, sans-serif' }}>
      <header style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button onClick={() => setPage('chat')}>Чат</button>
        <button onClick={() => setPage('settings')}>Настройки</button>
      </header>
      {page === 'chat' ? <ChatPage /> : <SettingsPage />}
    </main>
  );
}
