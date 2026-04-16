import { type ReactNode } from 'react';
import { useChatStore } from '../store/chatStore';

interface NavItem {
  path: string;
  label: string;
  icon?: ReactNode;
}

interface SidebarProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

function CheckBadgeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      style={{ width: 18, height: 18 }}
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12.75 11.25 15 15 9.75m6 2.25a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-3.75-7.5a2.25 2.25 0 0 0-2.25-2.25h-6a2.25 2.25 0 0 0-2.25 2.25v.372a2.25 2.25 0 0 1-.659 1.591l-.264.264a2.25 2.25 0 0 0 0 3.182l.264.264c.422.422.659.995.659 1.591v.372a2.25 2.25 0 0 0 2.25 2.25h6a2.25 2.25 0 0 0 2.25-2.25v-.372c0-.597.237-1.169.659-1.591l.264-.264a2.25 2.25 0 0 0 0-3.182l-.264-.264a2.25 2.25 0 0 1-.659-1.591v-.372Z"
      />
    </svg>
  );
}

const navItems: NavItem[] = [
  { path: '/', label: 'Чат' },
  { path: '/settings', label: 'Настройки' },
  { path: '/generate/tk', label: 'Генерация ТК' },
  { path: '/generate/letter', label: 'Генерация письма' },
  { path: '/generate/ks', label: 'Генерация КС' },
  { path: '/handover', label: 'Сдача объекта', icon: <CheckBadgeIcon /> }
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
              fontWeight: currentPath === item.path ? 700 : 400,
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}
          >
            {item.icon}
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
