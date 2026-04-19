import { type ReactNode, useState } from 'react';
import { useChatStore } from '../store/chatStore';
import Button from './ui/Button';
import { colors, radius, spacing, transitions, typography } from '../styles/tokens';

interface NavItem {
  path: string;
  label: string;
  icon: ReactNode;
}

interface SidebarProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

function BaseIcon({ children }: { children: ReactNode }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} style={{ width: 18, height: 18 }} aria-hidden>
      {children}
    </svg>
  );
}

const ChatIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M8.625 9.75h6.75m-6.75 3h4.5m6.375-.75a8.25 8.25 0 1 1-3.955-7.052c.707.42 1.61.183 2.023-.524a.75.75 0 0 1 1.3.75A9.733 9.733 0 0 0 21 12c0 5.385-4.365 9.75-9.75 9.75A9.75 9.75 0 0 1 1.5 12c0-5.385 4.365-9.75 9.75-9.75 1.804 0 3.494.49 4.945 1.343" /></BaseIcon>;
const SettingsIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M11.983 5.25c.483-1.041 1.964-1.041 2.447 0l.407.877a1.5 1.5 0 0 0 1.126.84l.969.142c1.15.168 1.607 1.58.774 2.392l-.701.684a1.5 1.5 0 0 0-.43 1.328l.166.963c.197 1.146-1.007 2.02-2.035 1.48l-.866-.455a1.5 1.5 0 0 0-1.396 0l-.866.455c-1.028.54-2.232-.334-2.035-1.48l.166-.963a1.5 1.5 0 0 0-.43-1.328l-.701-.684c-.833-.812-.376-2.224.774-2.392l.969-.142a1.5 1.5 0 0 0 1.126-.84l.406-.877ZM13.2 12a1.2 1.2 0 1 1-2.4 0 1.2 1.2 0 0 1 2.4 0Z" /></BaseIcon>;
const TKIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.75h6l3 3v13.5H7.5V3.75Zm6 0v3h3M9.75 14.25l4.5-4.5 1.5 1.5-4.5 4.5H9.75v-1.5Z" /></BaseIcon>;
const LetterIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5v10.5H3.75V6.75Zm0 0 8.25 6 8.25-6" /></BaseIcon>;
const KSIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 5.25h15v13.5h-15V5.25Zm0 4.5h15M10.5 5.25v13.5" /></BaseIcon>;
const HandoverIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m6 2.25a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></BaseIcon>;
const KnowledgeBaseIcon = () => <BaseIcon><path strokeLinecap="round" strokeLinejoin="round" d="M6 4.5h9l3 3v12H6v-15Zm9 0v3h3M8.25 13.5h7.5m-7.5-3h7.5" /></BaseIcon>;

const navItems: NavItem[] = [
  { path: '/', label: 'Чат', icon: <ChatIcon /> },
  { path: '/settings', label: 'Настройки', icon: <SettingsIcon /> },
  { path: '/generate/tk', label: 'Генерация ТК', icon: <TKIcon /> },
  { path: '/generate/letter', label: 'Генерация письма', icon: <LetterIcon /> },
  { path: '/generate/ks', label: 'Генерация КС', icon: <KSIcon /> },
  { path: '/handover', label: 'Сдача объекта', icon: <HandoverIcon /> },
  { path: '/knowledge-base', label: 'База знаний', icon: <KnowledgeBaseIcon /> }
];

export default function Sidebar({ currentPath, onNavigate }: SidebarProps) {
  const sessions = useChatStore((s) => s.sessions);
  const resetSession = useChatStore((s) => s.resetSession);
  const [hoveredSession, setHoveredSession] = useState<string | null>(null);

  return (
    <aside
      style={{
        width: 240,
        flexShrink: 0,
        height: '100vh',
        position: 'sticky',
        top: 0,
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'hidden',
        borderRight: `1px solid ${colors.border}`,
        padding: spacing.md,
        background: colors.bgSidebar,
        borderRadius: radius.lg
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: spacing.sm,
          marginBottom: spacing.lg,
          paddingBottom: spacing.md,
          borderBottom: `1px solid ${colors.border}`
        }}
      >
        <span style={{ fontSize: 20 }}>🏗️</span>
        <span style={{ fontWeight: 700, fontSize: 15, color: colors.primary }}>Construction AI</span>
      </div>
      <h3 style={{ margin: 0, marginBottom: spacing.md }}>Разделы</h3>
      <nav style={{ display: 'grid', gap: spacing.xs, marginBottom: spacing.lg }}>
        {navItems.map((item) => {
          const active = currentPath === item.path;
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => onNavigate(item.path)}
              style={{
                textAlign: 'left',
                fontWeight: active ? 600 : 500,
                display: 'flex',
                alignItems: 'center',
                gap: spacing.sm,
                border: 'none',
                borderLeft: `3px solid ${active ? colors.primary : 'transparent'}`,
                background: active ? colors.bgActiveNav : 'transparent',
                color: colors.textPrimary,
                borderRadius: radius.md,
                padding: `${spacing.sm}px ${spacing.sm}px ${spacing.sm}px ${spacing.md}`,
                cursor: 'pointer',
                fontFamily: typography.fontFamily,
                transition: `background ${transitions.fast}, color ${transitions.fast}`
              }}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </nav>

      <Button onClick={resetSession} style={{ width: '100%', marginBottom: spacing.md }}>
        <span aria-hidden>+</span> Новая сессия
      </Button>
      <h3 style={{ marginTop: 0, marginBottom: spacing.sm }}>История сессий</h3>
      <ul
        style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          display: 'grid',
          gap: spacing.xs,
          flex: 1,
          overflowY: 'auto',
          maxHeight: 'calc(100vh - 380px)'
        }}
      >
        {sessions.map((session) => {
          const isHovered = hoveredSession === session.id;
          return (
            <li key={session.id}>
              <button
                type="button"
                onClick={() => undefined}
                onMouseEnter={() => setHoveredSession(session.id)}
                onMouseLeave={() => setHoveredSession(null)}
                title={session.title}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  border: `1px solid ${isHovered ? colors.primary : colors.border}`,
                  borderRadius: radius.sm,
                  background: isHovered ? '#eff6ff' : '#fff',
                  color: colors.textSecondary,
                  padding: `${spacing.xs}px ${spacing.sm}px`,
                  cursor: 'pointer'
                }}
              >
                {session.title}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
