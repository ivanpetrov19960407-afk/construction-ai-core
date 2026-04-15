import { useChatStore } from '../store/chatStore';

interface NavItem {
  path: string;
  label: string;
}

interface SidebarProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

const navItems: NavItem[] = [
  { path: '/', label: 'Чат' },
  { path: '/settings', label: 'Настройки' },
  { path: '/generate/tk', label: 'Генерация ТК' },
  { path: '/generate/letter', label: 'Генерация письма' },
  { path: '/generate/ks', label: 'Генерация КС' }
];

export default function Sidebar({ currentPath, onNavigate }: SidebarProps) {
  const sessions = useChatStore((s) => s.sessions);
  const resetSession = useChatStore((s) => s.resetSession);

  return (
    <aside style={{ minWidth: 260, borderRight: '1px solid #ddd', paddingRight: 12 }}>
      <h3 style={{ marginTop: 0 }}>Разделы</h3>
      <nav style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
        {navItems.map((item) => (
          <button
            key={item.path}
            onClick={() => onNavigate(item.path)}
            style={{
              textAlign: 'left',
              fontWeight: currentPath === item.path ? 700 : 400
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

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
