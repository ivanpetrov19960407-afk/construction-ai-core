import ChatWindow from '../components/ChatWindow';
import RoleSelector from '../components/RoleSelector';

export default function ChatPage() {
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <RoleSelector />
      <ChatWindow />
    </div>
  );
}
