import { useChatStore, type ChatRole } from '../store/chatStore';

const ROLES: Array<{ id: ChatRole; label: string }> = [
  { id: 'estimator', label: 'Сметчик' },
  { id: 'lawyer', label: 'Юрист' },
  { id: 'engineer', label: 'Инженер' },
  { id: 'manager', label: 'Менеджер' }
];

export default function RoleSelector() {
  const role = useChatStore((s) => s.role);
  const setRole = useChatStore((s) => s.setRole);

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
      {ROLES.map((item) => (
        <button
          key={item.id}
          onClick={() => setRole(item.id)}
          style={{ fontWeight: role === item.id ? 700 : 400 }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
