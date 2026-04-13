import { useChatStore } from '../store/chatStore';

export default function Sidebar() {
  const sessions = useChatStore((s) => s.sessions);
  const resetSession = useChatStore((s) => s.resetSession);

  return (
    <aside style={{ minWidth: 240, borderRight: '1px solid #ddd', paddingRight: 12 }}>
      <button onClick={resetSession} style={{ width: '100%', marginBottom: 10 }}>
        + Новая сессия
      </button>
      <h3>История сессий</h3>
      <ul style={{ paddingInlineStart: 20 }}>
        {sessions.map((session) => (
          <li key={session.id}>{session.title}</li>
        ))}
      </ul>
    </aside>
  );
}
